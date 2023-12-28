import socket
import base64

from util import status_codes, write_data

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as pad


def build_non_body(before_body: str):
    lines = before_body.split('\r\n')
    method, url, http_type = lines[0].split(' ')
    headers = {}
    for header in lines[1:]:
        parts = header.split(":", 1)
        # If the header is not in the format of "key: value", ignore it
        if len(parts) != 2:
            break
        headers[parts[0].strip()] = parts[1].strip()
    return method, url, http_type, headers


class Request:
    # a simple request class containing method, url and headers
    def __init__(self, method: str, url: str, headers: {str: str}, body: bytes, http_type: str):
        self.method = method  # GET, POST, PUT, DELETE
        self.url = url  # e.g. /index.html
        self.headers = headers
        self.body = body  # In BINARY
        self.http_type = http_type  # idk why we use this

    def info(self):
        print(f"request method: {self.method}")
        print(f"request url: {self.url}")
        # print(f'body: {self.body}')
        for k, v in self.headers.items():
            print(f'{k}: {v}')

    @classmethod
    def from_socket(cls, sock: socket.socket) -> "Request":
        # First we try to extract the data before the body part
        data = sock.recv(1024)
        while data == b'':
            try:
                data = sock.recv(1024)
            except ConnectionResetError:
                pass
        # Then divide it into headers and the partial body
        before_body_part, partial_body = data.split(b'\r\n\r\n', 1)

        before_body_part = before_body_part.decode('utf-8')
        print('What we got for before body part: ', before_body_part)
        method, url, http_type, headers = build_non_body(before_body_part)

        # If the method is POST, the content length may exceed 1024, we need to obtain the remaining part.
        # Otherwise, partial body is the whole body, it can be empty
        body = partial_body
        if method == 'POST':
            # Then we complete the remaining body
            unreceived_data_bytes = int(headers['Content-Length']) - len(partial_body)
            while unreceived_data_bytes > 0:
                body += sock.recv(512)
                unreceived_data_bytes -= 512
        else:
            # do nothing.
            pass

        return cls(method, url, headers, body, http_type)


class Response:
    # a simple response class containing status code, headers and body
    def __init__(self):
        self.status_code = 200
        self.body = b"OK."
        self.headers = {"Connection": "keep-alive"}
        # The connection will be closed only when the client sends a "Connection: close" header.
        self.encryption = False
        self.symmetric_key = None
        self.iv = None

    def generate_status_line(self):
        return "HTTP/1.1 " + status_codes[self.status_code] + '\r\n'

    def set_strbody(self, body):
        """
        Set the body from a str content.
        :param body: In str format.
        """
        if self.encryption:
            # use symmetric key to encrypt body
            # encrypt body
            cipher = Cipher(algorithms.AES(self.symmetric_key), modes.CBC(self.iv), backend=default_backend())
            encryptor = cipher.encryptor()
            block_size = cipher.algorithm.block_size // 8
            padder = pad.PKCS7(block_size * 8).padder()
            body = padder.update(body.encode('utf-8')) + padder.finalize()
            body = base64.b64encode(encryptor.update(body) + encryptor.finalize()).decode('utf-8')
        self.body = body.encode("utf-8")
        print("encrypted body", self.body)

    def set_bbody(self, body):
        """
        Set the body from a bytes content.
        :param body: In bytes format.
        """
        self.body = body

    def set_content_type(self, content_type):
        self.headers["Content-Type"] = content_type

    def set_header(self, header, content):
        self.headers[header] = content

    def set_unauthorized(self):
        self.status_code = 401
        self.set_header("WWW-Authenticate", "Basic realm=\"Authorization Required\"")
        self.set_strbody("<h1>401 Unauthorized</h1>")

    def generate_error_page(self):
        if self.status_code == 401:
            self.set_unauthorized()
        elif self.status_code in (400, 403, 404, 405, 416, 502, 503):
            self.set_strbody("<h1>" + status_codes[self.status_code] + "</h1>")

    def generate_response_bytes(self):
        self.set_header('Content-Length', len(self.body))
        head = self.generate_status_line()
        head += "\r\n".join("{}: {}".format(k, v) for k, v in self.headers.items())
        head += "\r\n\r\n"
        return head.encode("utf-8") + self.body


def get_response_by_error_code(code: int) -> Response:
    response = Response()
    response.status_code = code
    response.generate_error_page()
    return response
