import http.server
import ssl
import socket
import json

def get_local_ip():
    """获取本机局域网 IP 地址"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

class LoggingHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """自定义 Handler，增加 /log 接口以接收手机网页端的调试日志"""
    
    def log_message(self, format, *args):
        """静默默认的 HTTP 请求访问日志"""
        pass
        
    def do_POST(self):
        if self.path == '/log':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                log_data = json.loads(post_data.decode('utf-8'))
                log_type = log_data.get('type', 'INFO').upper()
                msg = log_data.get('message', '')
                
                # 在控制台以高亮格式打印手机端的日志
                if log_type == 'ERROR':
                    print(f"\n🚨 [手机网页 ERROR] {msg}")
                    if 'error' in log_data:
                        print(f"   堆栈信息: {log_data['error']}")
                else:
                    print(f"📱 [手机网页 {log_type}] {msg}")
                    
            except Exception as e:
                print(f"[-] 解析手机日志出错: {e}")
                
            # 响应客户端
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_error(404, "File Not Found")

def main():
    port = 8443
    server_address = ('0.0.0.0', port)
    
    # 使用自定义的带日志接收功能的 Handler
    httpd = http.server.HTTPServer(server_address, LoggingHTTPRequestHandler)
    
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        ssl_context.load_cert_chain(certfile='cert.pem', keyfile='key.pem')
    except Exception as e:
        print("[-] 加载证书失败！请确保 cert.pem 和 key.pem 存在。")
        print(f"    错误详情: {e}")
        return

    httpd.socket = ssl_context.wrap_socket(httpd.socket, server_side=True)
    
    local_ip = get_local_ip()
    print("=== 极简 HTTPS 本地网页服务端 (带日志回显) ===")
    print(f"[+] 正在运行在端口: {port}")
    print(f"[+] 本地访问地址: https://localhost:{port}")
    print(f"[+] 手机访问地址: https://{local_ip}:{port}")
    print("\n手机端打开网页后的所有操作日志与报错都会实时输出在下方：\n")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] 正在关闭 HTTPS 服务端...")
        httpd.server_close()
        print("[+] 已安全退出。")

if __name__ == "__main__":
    main()
