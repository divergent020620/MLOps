"""
Cube Studio Dataset — Jupyter Server Extension

向 JupyterLab 页面注入 Cube Studio 后端 API 地址，
供前端 labextension (cube-studio-dataset) 使用。

用法:
    pip install cube_studio_dataset/
    jupyter serverextension enable --py cube_studio_dataset --sys-prefix
"""
import os


def _jupyter_server_extension_paths():
    return [{"module": "cube_studio_dataset"}]


def _load_jupyter_server_extension(lab_app):
    """注入 _cube_studio_api 全局变量到页面。"""
    cube_api = os.getenv('CUBE_STUDIO_API', '/dataset_modelview/api')

    if hasattr(lab_app, 'web_app'):
        from tornado.web import OutputTransform

        api_script = f'<script>window._cube_studio_api="{cube_api}";</script>'
        js_bytes = api_script.encode('utf-8')

        class _CubeStudioConfig(OutputTransform):
            def transform_first_chunk(self, status_code, headers, chunk, finishing):
                ctype = headers.get('Content-Type', '')
                if 'text/html' in ctype and b'</head>' in chunk and b'_cube_studio_api' not in chunk:
                    chunk = chunk.replace(b'</head>', js_bytes + b'\n</head>')
                return status_code, headers, chunk

        try:
            lab_app.web_app.add_transform(_CubeStudioConfig())
        except Exception:
            pass

    lab_app.log.info(f'[Cube Studio] server extension loaded, API={cube_api}')
