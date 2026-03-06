"""
serve_dashboard.py — Serve the dashboard with environment variables injected

This script reads the treasury address from .env and injects it into
the dashboard HTML before serving it. Also provides API endpoint for
paper portfolio data.

Usage:
    python serve_dashboard.py
    # Then open http://localhost:8000
"""
import os
import json
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from dotenv import load_dotenv

load_dotenv()

TREASURY_ADDRESS = os.getenv('TREASURY_ADDRESS', '0x0000000000000000000000000000000000000000')
PORTFOLIO_FILE = Path('paper_portfolio.json')

class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            with open('index.html', 'r', encoding='utf-8') as f:
                html = f.read()
            
            # Inject treasury address
            html = html.replace(
                "const treasuryAddress = 'YOUR_TREASURY_ADDRESS_HERE';",
                f"const treasuryAddress = '{TREASURY_ADDRESS}';"
            )
            
            self.wfile.write(html.encode('utf-8'))
        
        elif self.path == '/api/portfolio':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # Load portfolio data
            if PORTFOLIO_FILE.exists():
                try:
                    data = json.loads(PORTFOLIO_FILE.read_text())
                    
                    # Calculate stats
                    starting = data.get('starting_balance', 1000.0)
                    cash = data.get('cash_usd', starting)
                    positions = data.get('positions', {})
                    trades = data.get('trades', [])
                    
                    # Calculate total value (cash + positions at last known prices)
                    total_value = cash
                    position_list = []
                    for sym, pos in positions.items():
                        pos_value = pos['quantity'] * pos['avg_buy_price']
                        total_value += pos_value
                        unrealized = pos_value - pos['total_cost']
                        position_list.append({
                            'symbol': sym,
                            'quantity': pos['quantity'],
                            'unrealized_pnl': unrealized
                        })
                    
                    # Calculate win rate
                    sell_trades = [t for t in trades if t.get('action') == 'SELL' and t.get('pnl') is not None]
                    wins = [t for t in sell_trades if t['pnl'] >= 0]
                    win_rate = (len(wins) / len(sell_trades) * 100) if sell_trades else 0
                    
                    response = {
                        'total_value': total_value,
                        'total_pnl': total_value - starting,
                        'win_rate': win_rate,
                        'total_trades': len(trades),
                        'positions': position_list
                    }
                    
                    self.wfile.write(json.dumps(response).encode('utf-8'))
                except Exception as e:
                    self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
            else:
                # No portfolio file yet
                response = {
                    'total_value': 1000.0,
                    'total_pnl': 0.0,
                    'win_rate': 0.0,
                    'total_trades': 0,
                    'positions': []
                }
                self.wfile.write(json.dumps(response).encode('utf-8'))
        
        else:
            super().do_GET()

if __name__ == '__main__':
    PORT = 8000
    print(f"🐜 Ant Colony Finance Dashboard")
    print(f"   Treasury: {TREASURY_ADDRESS}")
    print(f"   Server:   http://localhost:{PORT}")
    print(f"\nPress Ctrl+C to stop")
    
    server = HTTPServer(('localhost', PORT), DashboardHandler)
    server.serve_forever()
