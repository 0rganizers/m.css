#
#   This file is part of m.css.
#
#   Copyright © 2017, 2018 Vladimír Vondruš <mosra@centrum.cz>
#
#   Permission is hereby granted, free of charge, to any person obtaining a
#   copy of this software and associated documentation files (the "Software"),
#   to deal in the Software without restriction, including without limitation
#   the rights to use, copy, modify, merge, publish, distribute, sublicense,
#   and/or sell copies of the Software, and to permit persons to whom the
#   Software is furnished to do so, subject to the following conditions:
#
#   The above copyright notice and this permission notice shall be included
#   in all copies or substantial portions of the Software.
#
#   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#   IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#   FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
#   THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#   LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#   FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#   DEALINGS IN THE SOFTWARE.
#

import pickle
import re
from hashlib import sha1

import latex2svg

# Extracted common code used by both dox2html5.py and the m.math plugin to
# avoid dependency of dox2html5.py on Pelican

# Modified params to use for math rendering
params = latex2svg.default_params.copy()
params.update({
    # Don't use libertine fonts as they mess up things
    'preamble': r"""
\usepackage[utf8x]{inputenc}
\usepackage{amsmath}
\usepackage{amsfonts}
\usepackage{amssymb}
\usepackage{gensymb}
\usepackage{newtxtext}
""",
    # Zoom the letters a bit to match page font size
    'dvisvgm_cmd': 'dvisvgm --no-fonts -Z 1.25',
    })

_patch_src = re.compile(r"""<\?xml version='1.0' encoding='UTF-8'\?>
<!-- This file was generated by dvisvgm \d+\.\d+\.\d+ -->
<svg height='(?P<height>[^']+)pt' version='1.1' viewBox='(?P<viewBox>[^']+)' width='(?P<width>[^']+)pt' xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink'>
""")

# version ignored by all UAs, safe to drop https://stackoverflow.com/a/18468348
_patch_dst = r"""<svg{attribs} style="width: {width:.3f}em; height: {height:.3f}em;{style}" viewBox="{viewBox}">
<title>
{formula}
</title>
"""

# 1 pt is 1.333 px, base font size is 16px. TODO: make this configurable,
# remove the 1.25 scaling
pt2em = 1.333333/16.0

_unique_src = re.compile(r"""(?P<name> id|xlink:href)='(?P<ref>#?)(?P<id>g\d+-\d+|page\d+)'""")
_unique_dst = r"""\g<name>='\g<ref>eq{counter}-\g<id>'"""

# Counter to ensure unique IDs for multiple SVG elements on the same page.
# Reset back to zero on start of a new page for reproducible behavior.
counter = 0

# Cache for rendered formulas (source formula sha1 -> (depth, svg data)). The
# counter is not included
_cache_version = 0
_cache = None

# Fetch cached formula or render it and add to the cache. The formula has to
# be already wrapped in $, $$ etc. environment.
def fetch_cached_or_render(formula):
    global _cache

    # Cache not used, pass through
    if not _cache:
        out = latex2svg.latex2svg(formula, params=params)
        return out['depth'], out['svg']

    hash = sha1(formula.encode('utf-8')).digest()
    if not hash in _cache[2]:
        out = latex2svg.latex2svg(formula, params=params)
        _cache[2][hash] = (_cache[1], out['depth'], out['svg'])
    else:
        _cache[2][hash] = (_cache[1], _cache[2][hash][1], _cache[2][hash][2])
    return (_cache[2][hash][1], _cache[2][hash][2])

def unpickle_cache(file):
    global _cache

    if file:
        with open(file, 'rb') as f:
            _cache = pickle.load(f)
    else:
        _cache = None

    # Reset the cache if not valid or not expected version
    if not _cache or _cache[0] != _cache_version:
        _cache = (_cache_version, 0, {})

    # Otherwise bump cache age
    else: _cache = (_cache[0], _cache[1] + 1, _cache[2])

def pickle_cache(file):
    global _cache

    # Don't save any file if there is nothing
    if not _cache or not _cache[2]: return

    # Prune entries that were not used
    cache_to_save = (_cache_version, _cache[1], {})
    for hash, entry in _cache[2].items():
        if entry[0] != _cache[1]: continue
        cache_to_save[2][hash] = entry

    with open(file, 'wb') as f:
        pickle.dump(cache_to_save, f)

# Patches the output from dvisvgm
# - w/o the XML preamble and needless xmlns attributes
# - unique element IDs (see `counter`)
# - adjusts vertical align if depth is not none
# - adds additional `attribs` to the <svg> element
def patch(formula, svg, depth, attribs):
    global counter
    counter += 1

    if depth is None: style = ''
    else: style = ' vertical-align: -{:.3f}em;'.format(depth*1.25)

    def repl(match):
        return _patch_dst.format(
            width=pt2em*float(match.group('width')),
            height=pt2em*float(match.group('height')),
            style=style,
            viewBox=match.group('viewBox'),
            attribs=attribs,
            formula=formula)

    return _unique_src.sub(_unique_dst.format(counter=counter), _patch_src.sub(repl, svg))
