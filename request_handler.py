import os

from code_template import render_page
from http_model import Request, Response, get_response_by_error_code
from util import extract_url_and_args, get_boundary, extract_every_part, extract_from_part
from auth_core import extract_usr_pass


root_dir = os.curdir + '/data'

HTML = "text/html"
FILE = "application/octet-stream"
TEXT = "text/plain"

def is_method_allowed(url, method):
    if url.startswith("/upload?") or url.startswith("/delete?"):
        if method != "POST":
            return False
    elif url.startswith("/") and url != "/":
        if method != "GET":
            return False
    return True

def gen_txt(path):
    # Response with the name of all items in list under the target directory
    # `["123.png", "666/", "abc.py", "favicon.ico"]` in this case.
    items = os.listdir(path)
    # Convert list to str
    items = str(items)
    return items


def file2bytes(path):
    body = b''
    with open(path, 'rb') as f:
        for line in f:
            body += line
    return body


class RequestHandler:
    def __init__(self, server, request):
        self.server = server
        self.request = request
        self.response = Response()
        self.response.set_content_type(HTML)

    def handle(self):
        if self.request.http_type.startswith('ENCRYPTION'):
            # # 自定义 encryption 协议
            # # 好孩子不要这么做，违法哟～
            # # 我认真的！
            # if self.encryption_handle(request, response, client_socket):
            #     response.encryption = True
            #     response.symmetric_key = self.client_symmetric_key[client_socket]
            #     response.iv = self.client_ivs[client_socket]
            #     response.set_strbody("encrypted response")
            #     self.auth_handle(request.headers, response)
            pass
        else:
            # Check method, 405 if failure
            if not is_method_allowed(self.request.url, self.request.method):
                return get_response_by_error_code(405)

            auth_core = self.server.auth_core
            auth_res = auth_core.authenticate_headers(self.request.headers)
            if auth_res == 200:
                self.response.status_code = 200
            elif auth_res == 401:
                return get_response_by_error_code(401)
            else:
                # Auth_res is the new session_id
                self.response.status_code = 200
                self.response.set_header('Set-Cookie', f'session-id={auth_res}')

        method = self.request.method
        if method == 'POST':
            self.post()
        elif method == 'GET':
            self.get()
        elif method == 'HEAD':
            self.head()
        else:
            return get_response_by_error_code(405)

        return self.response

    def post(self):
        url, kargs = extract_url_and_args(self.request.url)
        if url.startswith('/upload') or url.startswith('/delete'):
            if 'path' not in kargs:
                self.response = get_response_by_error_code(400)
                return

            path = kargs['path'].strip('/')
            username = path.split('/')[0]

            base64str = self.request.headers['Authorization'].split(" ")[1]
            usr_in_auth, _ = extract_usr_pass(base64str)

            # username in path must correspond to usr_in_auth.
            if usr_in_auth != username:
                print('username in path', f'{username}')
                print('username in authorization', f'{usr_in_auth}')
                self.response = get_response_by_error_code(403)
                return

            if url.startswith('/upload'):
                # Upload
                self.upload(path)
            else:
                # Delete
                self.delete(path)
        else:
            self.response.set_strbody('<h1>Other POST</h1>')

    def get(self):
        # http://localhost:8080/[access_path]?SUSTech-HTTP=[01]
        # access_path is the relative path under the /data/ folder
        # If the requested target is a folder, the SUSTech-HTTP parameter is OPTIONAL
        # If the requested target is a file, the SUSTech-HTTP parameter will be ignored
        enable = False

        relative_path, kargs = extract_url_and_args(self.request.url)
        path = root_dir + relative_path
        if os.path.isdir(path):
            if "SUSTech-HTTP" not in kargs or kargs["SUSTech-HTTP"] == '0':
                self.response.set_content_type(HTML)
                self.response.set_strbody(render_page(path, self.server.port, "http://localhost:8080/upload?path=", enable))
            elif kargs["SUSTech-HTTP"] == 1:
                # Response with the name of all items in list under the target directory
                self.response.set_content_type(TEXT)
                self.response.set_strbody(gen_txt(path))
        elif os.path.isfile(path):
            self.response.set_content_type(FILE)
            self.response.set_bbody(file2bytes(path))
        else:
            self.response = get_response_by_error_code(404)

    def head(self):
        self.response.set_strbody('<h1>Hello World</h1>')

    def upload(self, url):
        print('UPLOAD START')
        # upload url example: http://localhost:8080/upload?path=clientx/

        path = root_dir + '/' + url
        if not os.path.isdir(path):
            self.response = get_response_by_error_code(404)
            return

        # One possible format for multipart/form-data

        # ------WebKitFormBoundary7MA4YWxkTrZu0gW\r\n
        # Content-Disposition: form-data; name="firstfile"; filename="a.txt"\r\n
        # Content-Type: text/plain\r\n
        # \r\n
        # 123\r\n
        # ------WebKitFormBoundary7MA4YWxkTrZu0gW--\r\n

        # 其中------WebKitFormBoundary7MA4YWxkTrZu0gW是boundary，在request的header中
        # Content-Disposition: form-data; name="firstfile"; filename="a.txt"中的filename是文件名
        # \r\n\r\n之后的是文件内容, 即123\r\n

        # Get the boundary
        boundary = get_boundary(self.request.headers['Content-Type'])
        print('The boundary of the form is: ', boundary)
        # Extract every part, then extract the head and body, then write files.
        for part in extract_every_part(self.request.body, boundary):
            headers, body = extract_from_part(part)
            if 'Content-Disposition' in headers:
                filename = headers['Content-Disposition'].split("filename=")[1].strip('"')
            else:
                filename = os.urandom(10)

            with open(f'{path}/{filename}', 'wb') as f:
                f.write(body)
                f.close()

    def delete(self, url):
        # delete url: http://localhost:8080/delete?path=/clientx/samplefile
        # Check if the target file exist
        path = root_dir + "/" + url
        if not os.path.isfile(path):
            self.response = get_response_by_error_code(404)
            return
            # Delete the file
        os.remove(path)
        print('FILE ' + path + ' has been removed successfully'.upper())