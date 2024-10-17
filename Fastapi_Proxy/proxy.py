
from httpx import AsyncClient
from fastapi import Request, FastAPI
from fastapi.responses import StreamingResponse, Response
from starlette.background import BackgroundTask
import random, string
import re
import json
import logging
import urllib.parse
import html
import gzip
import brotli
import zlib
from urllib.parse import urlparse, parse_qs
import base64

formatter = logging.Formatter('[+] %(asctime)s %(levelname)s %(message)s')
app = FastAPI(
    openapi_url=None,
    docs_url=None,
    redoc_url=None
)

HTTP_SERVER = AsyncClient(base_url="http://service", follow_redirects=False, verify=False,timeout=600)



def setup_logger(name, log_file, level=logging.INFO):
    handler = logging.FileHandler(log_file)        
    handler.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)
    return logger


all_request_log = setup_logger('all_request_log', 'all_request.log')
flag_request_log = setup_logger('flag_request_log', 'flag_request.log')
blacklist_request_log = setup_logger('blacklist_request_log', 'blacklist_request.log')



def ran(N):
    return (''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(N))).encode()


def log_request(method, uri, headers, body, res_body = None, status = None, type_ = "all"):
    if type_ == "flag":
        headers_str = ""
        for h in headers:
            headers_str += f"{h}: {headers[h]}\n"
        template = f"\n##############START################\n{method} {uri}\n{headers_str}\n\n{body}\n###response###\n{res_body}\n###response###\n##############END################"
        flag_request_log.info(template)

    elif type_ == "black":
        headers_str = ""
        for h in headers:
            headers_str += f"{h}: {headers[h]}\n"
        template = f"\n##############START################\n{method} {uri}\n{headers_str}\n\n{body}\n###response###\n{res_body}\n###response###\n##############END################"
        blacklist_request_log.info(template)

    elif type_ == "all":
        # headers_str = json.dumps(headers)
        headers_str = ""
        for h in headers:
            headers_str += f"{h}: {headers[h]}\\n"
        body_bytes_sent = len(res_body)
        http_referer = headers['referer'] if 'referer' in headers else "-"
        http_x_forwarded_for = headers['x-forwarded-for'] if 'x-forwarded-for' in headers else "-"
        http_user_agent = headers['user-agent'] if 'user-agent' in headers else "-"

        template = f'"{method} {uri}" "{status}" "{body_bytes_sent}" "{http_referer}" "{http_user_agent}" "{http_x_forwarded_for}" "{headers_str}" "{body}"';
        # template = f"###URI###{method} {uri}###URI### ###headers###{headers_str}###headers### ###body###{body}###body###"
        all_request_log.info(template)
    
 

def marking_flag(string: bytes):
    # pattern = b"([a-fA-F\d]{32})"
    # re_string = string
    # matches = re.findall(pattern, re_string)
    # x = False
    # for match in matches:
    #     re_string = re_string.replace(match,ran(len(match)))
    #     x = True
    # return re_string, x
    return string, False

def check_request(method, uri, headers, body):
    # VD đề DF: http://192.168.205.130:8080/image-sharing/?f=NGxnd3E1LmpwZw%3D%3D ==> block 
    parsed_uri = urlparse(uri)
    params = parse_qs(parsed_uri.query)
    f = params['f'] if "f" in params else []
    for values in f:
        x = base64.b64decode(values)
        if b'flag' in x:
            return False

    # check in url
    black_list = [
        "/flag/flag"
    ]
    uri = html.unescape(urllib.parse.unquote(uri.lower()))
    for x in black_list:
        if x in uri:
            log_request(method, uri, headers, body, type_= "black")
            return False
        
    # check in body
    if b"/flag/flag" in body or 'child_process' in body:
        log_request(method, uri, headers, body, type_= "black")
        return False
    
    # check user agent
    black_user_agent = [
        "test"
    ]
    user_agent = headers['user-agent'] if 'user-agent' in headers else ''
    if user_agent in black_user_agent:
        return False

    return True


def content_encoding(content, alg):
    if alg == "gzip":
        forward_content = gzip.compress(content)
    elif alg == "br":
        forward_content = brotli.compress(content)
    elif alg == "deflate":
        forward_content = zlib.compress(content)
    elif alg == "compress":
        forward_content = content
    else:
        forward_content = content
    return forward_content


async def _reverse_proxy(request: Request):
    method = request.method
    uri = request.headers.get('raw-uri')
    headers_dict = {key.decode(): value.decode() for key, value in (request['headers'])}
    req_body = await request.body()

    if check_request(method, uri, headers_dict, req_body):
        rp_req = HTTP_SERVER.build_request(
            method,
            uri,
            headers=request.headers.raw,
            content=req_body
        )

        rp_resp = await HTTP_SERVER.send(rp_req, stream=False)
        res_body = rp_resp.content

        # sua contetn
        # forward_content, is_have_flag = marking_flag(res_body) 
        # xu ly content-encoding
        # content_encoding_alg = forward_headers.get('content-encoding','')
        # forward_content = content_encoding(forward_content,content_encoding_alg)
        # if is_have_flag:
        #     # print("flag_found")
        #     task = BackgroundTask(log_request, method, uri, headers_dict, req_body, res_body, forward_status, "flag")
        # else:
        #     task=None

        task = None
        
        forward_headers = rp_resp.headers
        forward_status = rp_resp.status_code
        # encoding lại theo content-encoding
        forward_content = content_encoding(res_body,forward_headers.get('content-encoding',''))
        forward_headers['content-length'] = str(len(forward_content)) # cap nhat content len

    
        # Log all request
        log_request(method, uri, headers_dict, req_body, res_body, forward_status, "all")
        
        # fix looix set_cookie truongw hop service dung cookie
        if 'set-cookie' in forward_headers: 
            cook = forward_headers.pop("set-cookie")
            forward_res = Response(
                content=forward_content,
                status_code=forward_status,
                headers=forward_headers,
                background=task,
            )
            list_cook =cook.split(", ")
            for c in list_cook:
                forward_res.raw_headers.append((b"set-cookie", c.encode("utf-8")))
        else:
            forward_res = Response(
                    content=forward_content,
                    status_code=forward_status,
                    headers=forward_headers,
                    background=task,
                )
        return forward_res

    else:
        log_request(method, uri, headers_dict, req_body, "Forbidden", 403, "all")
        return Response(
            content="Cố lên các bạn trẻ!",
            status_code=200
            )
    

app.add_route("/{path:path}", _reverse_proxy, ["GET", "POST", "PUT", "DELETE", "OPTIONS"])

# uvicorn --host 0.0.0.0 --port 5000 --reload proxy:app --no-server-header --no-date-header
