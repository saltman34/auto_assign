'''Static UI asset paths and small loaders.

Centralized so `page.py`, `__init__.py`, and any future page can reach the logo
and favicon through one import. Keeps asset-path knowledge out of the theme,
navigation, and page modules.
'''
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

_ASSETS_DIR = Path(__file__).resolve().parent / 'assets'

LOGO_PATH: Path = _ASSETS_DIR / 'logo.png'
'''Full-resolution square PNG (transparent background) for in-page usage.'''

FAVICON_PATH: Path = _ASSETS_DIR / 'favicon.png'
'''256x256 PNG used as the browser-tab / PWA icon via ``st.set_page_config``.'''


@lru_cache(maxsize=1)
def logo_data_uri() -> str:
    '''Return a ``data:image/png;base64,...`` URI for inline HTML embedding.

    Used by the sidebar brand block, which renders via ``st.markdown(..., unsafe_allow_html=True)``
    and therefore cannot reference a local file path directly.
    '''
    encoded = base64.b64encode(LOGO_PATH.read_bytes()).decode('ascii')
    return f'data:image/png;base64,{encoded}'


@lru_cache(maxsize=1)
def load_favicon() -> 'PILImage':
    '''Return the favicon as a PIL image, cached for the life of the process.'''
    from PIL import Image

    return Image.open(FAVICON_PATH)
