#!/usr/bin/env python3
"""Simple HTTP server for the test application."""

import http.server
import socketserver
import webbrowser
import os
from pathlib import Path

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers for local development
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

def start_test_server(port=8080):
    """Start the test application server."""
    # Change to the test-app directory
    os.chdir(Path(__file__).parent)
    
    with socketserver.TCPServer(("", port), CustomHTTPRequestHandler) as httpd:
        print(f"Starting test server at http://localhost:{port}")
        print(f"Test application: http://localhost:{port}/index.html")
        print("Press Ctrl+C to stop the server")
        
        # Open browser automatically
        try:
            webbrowser.open(f'http://localhost:{port}/index.html')
        except:
            pass
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped by user")

if __name__ == "__main__":
    start_test_server()