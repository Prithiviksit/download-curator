"""
Lightweight local HTTP API Server for download-curator.
Allows the native macOS menu-bar UI and background service to interact loosely coupled.
Uses standard library http.server for zero extra heavy dependencies.
"""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from download_curator.core.engine import CuratorEngine
from download_curator.core.models import ProposalStatus

logger = logging.getLogger("download_curator.server")


class CuratorAPIHandler(BaseHTTPRequestHandler):
    """Handles REST API requests from the macOS Menu Bar UI."""

    engine: CuratorEngine  # Injected on server start

    def _send_json_response(self, data: Any, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        payload = json.dumps(data, default=str)
        self.wfile.write(payload.encode("utf-8"))

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path_parts = [p for p in parsed_url.path.strip("/").split("/") if p]

        # GET /api/status
        if path_parts == ["api", "status"]:
            pending = self.engine.get_pending_proposals()
            self._send_json_response(
                {
                    "status": "online",
                    "pending_count": len(pending),
                    "watch_directory": str(self.engine.config.watch_directory),
                    "destination_root": str(self.engine.config.destination_root),
                }
            )
            return

        # GET /api/proposals/pending
        if path_parts == ["api", "proposals", "pending"]:
            pending = self.engine.get_pending_proposals()
            self._send_json_response([p.model_dump() for p in pending])
            return

        # GET /api/proposals/<id>
        if len(path_parts) == 3 and path_parts[:2] == ["api", "proposals"] and path_parts[2].isdigit():
            prop_id = int(path_parts[2])
            prop = self.engine.get_proposal(prop_id)
            if prop:
                self._send_json_response(prop.model_dump())
            else:
                self._send_json_response({"error": "Proposal not found"}, status=404)
            return

        # GET /api/history
        if path_parts == ["api", "history"]:
            history = self.engine.get_history(limit=50)
            self._send_json_response([h.model_dump() for h in history])
            return

        self._send_json_response({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        parsed_url = urlparse(self.path)
        path_parts = [p for p in parsed_url.path.strip("/").split("/") if p]

        content_length = int(self.headers.get("Content-Length", 0))
        body = {}
        if content_length > 0:
            raw_body = self.wfile if False else self.rfile.read(content_length)
            try:
                body = json.loads(raw_body.decode("utf-8"))
            except Exception:
                pass

        # POST /api/scan
        if path_parts == ["api", "scan"]:
            proposals = self.engine.scan(dry_run=False)
            self._send_json_response(
                {
                    "message": f"Scan completed. Found {len(proposals)} proposals.",
                    "proposals": [p.model_dump() for p in proposals],
                }
            )
            return

        # POST /api/undo
        if path_parts == ["api", "undo"]:
            try:
                restored = self.engine.undo()
                self._send_json_response(
                    {"message": f"Successfully undone last action.", "restored_path": str(restored)}
                )
            except Exception as e:
                self._send_json_response({"error": str(e)}, status=400)
            return

        # POST /api/restart (Reload config & AI provider)
        if path_parts == ["api", "restart"]:
            try:
                from download_curator.config import load_config
                from download_curator.ai.provider_factory import get_ai_provider
                new_cfg = load_config()
                self.engine.config = new_cfg
                self.engine.ai_provider = get_ai_provider(new_cfg)
                self._send_json_response(
                    {
                        "message": "Configuration reloaded successfully.",
                        "provider": new_cfg.ai.provider,
                        "model": new_cfg.ai.model,
                    }
                )
            except Exception as e:
                self._send_json_response({"error": str(e)}, status=400)
            return

        # Proposal specific actions: /api/proposals/<id>/<action>
        if len(path_parts) == 4 and path_parts[:2] == ["api", "proposals"] and path_parts[2].isdigit():
            prop_id = int(path_parts[2])
            action = path_parts[3]

            if action == "approve":
                custom_fn = body.get("proposed_filename")
                custom_dst = body.get("proposed_destination")
                try:
                    final_path = self.engine.approve_proposal(
                        proposal_id=prop_id,
                        custom_filename=custom_fn,
                        custom_destination=custom_dst,
                    )
                    self._send_json_response(
                        {
                            "success": True,
                            "proposal_id": prop_id,
                            "final_path": str(final_path),
                        }
                    )
                except Exception as e:
                    self._send_json_response({"error": str(e)}, status=400)
                return

            elif action == "reject":
                success = self.engine.reject_proposal(prop_id)
                self._send_json_response({"success": success, "proposal_id": prop_id})
                return

            elif action == "ignore":
                success = self.engine.ignore_file(prop_id)
                self._send_json_response({"success": success, "proposal_id": prop_id})
                return

            elif action == "ai_enhance":
                try:
                    updated = self.engine.enhance_with_ai(prop_id)
                    self._send_json_response(updated.model_dump())
                except Exception as e:
                    self._send_json_response({"error": str(e)}, status=400)
                return

            elif action == "edit":
                updated = self.engine.edit_proposal(
                    prop_id,
                    proposed_filename=body.get("proposed_filename"),
                    proposed_destination=body.get("proposed_destination"),
                    category=body.get("category"),
                )
                if updated:
                    self._send_json_response(updated.model_dump())
                else:
                    self._send_json_response({"error": "Failed to edit proposal"}, status=400)
                return

        self._send_json_response({"error": "Not found"}, status=404)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy standard HTTP access logs in terminal
        pass


def run_server(engine: CuratorEngine, host: str = "127.0.0.1", port: int = 58291) -> None:
    """Run the API server loop."""
    CuratorAPIHandler.engine = engine
    server_address = (host, port)
    httpd = HTTPServer(server_address, CuratorAPIHandler)
    logger.info(f"download-curator API server running on http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
