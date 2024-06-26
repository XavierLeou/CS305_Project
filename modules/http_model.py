import socket
from modules.status_codes import status_codes

from modules.util import display_some


def build_head(head: str) -> list[str, str, str, dict]:
    """
    Extract method, url, http_type and headers from the head.
    :param head: The head of an http request
    :return: Method, url, http_type and headers
    """
    lines = head.split('\r\n')
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
        self.method = method  # GET, POST, HEAD
        self.url = url  # e.g. /index.html
        self.headers = headers
        self.body = body  # In BINARY
        self.http_type = http_type  # idk why we use this

    def to_bytes(self):
        body = f'{self.method} {self.url} {self.http_type}\r\n'
        headers = '\r\n'.join('{}: {}'.format(k, v) for k, v in self.headers.items())
        if headers == '':
            body += '\r\n'
        else:
            body += headers + '\r\n\r\n'
        return body.encode('utf-8') + self.body

    @classmethod
    def from_socket(cls, sock: socket.socket) -> "Request":
        # First we try to extract the data before the body part
        # We try to extract the first 1024 bytes. In most cases, head will not exceed 4096 bytes.
        # In this project, it is mandatory that the head(including\r\n\r\n) must not exceed 4096.
        data = sock.recv(8192)
        if data == b'':
            # That means the connection is about to close.
            return None
        # Then divide it into headers and the partial body
        parts = data.split(b'\r\n\r\n', 1)
        head_part = parts[0]
        partial_body = b'' if len(parts) == 1 else parts[1]
        head_part = head_part.decode('utf-8')
        body = partial_body

        # If the method is POST, the content length may exceed 4096, we need to obtain the remaining part.
        # Otherwise, partial body is the whole body, it can be empty
        method, url, http_type, headers = build_head(head_part)
        if 'Content-Length' in headers:
            while len(body) < int(headers['Content-Length']):
                body += sock.recv(4096)
        print('--Request:')
        print(head_part)
        display_some(body)
        print('--EOF-Request--\n')
        return cls(method, url, headers, body, http_type)


class Response:
    # a simple response class containing status code, headers and body
    def __init__(self):
        self.status_code = 200
        self.body = b"OK."
        # The connection will be closed only when the client sends a "Connection: close" header.
        self.headers = {'Connection': 'keep-alive',
                        'Accept-Ranges': 'bytes',
                        'Content-Type': 'text/html'}

    def generate_status_line(self):
        return "HTTP/1.1 " + status_codes[self.status_code] + '\r\n'

    def set_strbody(self, body):
        """
        Set the body from a str content.
        :param body: In str format.
        """
        self.body = body.encode("utf-8")

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

    def build_length_or_chunked(self):
        if 'Transfer-Encoding' in self.headers and self.headers['Transfer-Encoding'] == 'chunked':
            # No need to set Content-Length
            pass
        else:
            self.set_header('Content-Length', len(self.body))

    def to_bytes(self):
        head = self.generate_status_line()
        headers = "\r\n".join("{}: {}".format(k, v) for k, v in self.headers.items())
        if headers == '':
            head += '\r\n'
        else:
            head += headers + '\r\n\r\n'
        return head.encode('utf-8') + self.body


def get_response_by_error_code(code: int) -> Response:
    response = Response()
    response.status_code = code
    response.generate_error_page()
    response.build_length_or_chunked()
    return response


def get_response_200(body: bytes) -> Response:
    response = Response()
    response.body = body
    response.build_length_or_chunked()
    return response
