from waitress import serve
from app import app
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=3000)
    parser.add_argument('--host', type=str, default='0.0.0.0')
    args = parser.parse_args()
    
    print(f"Starting production server on {args.host}:{args.port}")
    serve(app, host=args.host, port=args.port) 