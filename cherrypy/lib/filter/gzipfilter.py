"""
Copyright (c) 2004, CherryPy Team (team@cherrypy.org)
All rights reserved.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

    * Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
    * Neither the name of the CherryPy Team nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

import gzip, StringIO
from basefilter import BaseOutputFilter
from cherrypy import cpg

class GzipFilter(BaseOutputFilter):
    """
    Filter that gzips the response.
    """

    def __init__(self, mimeTypeList = ['text/html']):
        # List of mime-types to compress
        self.mimeTypeList = mimeTypeList

    def beforeResponse(self):
        if not cpg.response.body:
            # Response body is empty (might be a 304 for instance)
            return
        ct = cpg.response.headerMap.get('Content-Type').split(';')[0]
        ae = cpg.request.headerMap.get('Accept-Encoding', '')
        if (ct in self.mimeTypeList) and ('gzip' in ae):
            # Set header
            cpg.response.headerMap['Content-Encoding'] = 'gzip'
            # Compress page
            zbuf = StringIO.StringIO()
            zfile = gzip.GzipFile(mode='wb', fileobj = zbuf, compresslevel = 9)
            zfile.write(cpg.response.body)
            zfile.close()
            cpg.response.body = zbuf.getvalue()


