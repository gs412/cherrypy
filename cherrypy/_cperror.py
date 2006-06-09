"""Error classes for CherryPy."""

import cgi
import sys
import traceback
import urlparse

from cherrypy.lib import httptools


class Error(Exception):
    pass

class WrongConfigValue(Error):
    """ Happens when a config value can't be parsed, or is otherwise illegal. """
    pass

class InternalRedirect(Exception):
    """Exception raised when processing should be handled by a different path.
    
    If you supply a query string, it will be replace request.params.
    If you omit the query string, the params from the original request will
    remain in effect.
    """
    
    def __init__(self, path):
        import cherrypy
        request = cherrypy.request
        
        if "?" in path:
            # Pop any params included in the path
            path, pm = path.split("?", 1)
            request.query_string = pm
            request.params = httptools.parseQueryString(pm)
        
        # Note that urljoin will "do the right thing" whether url is:
        #  1. a URL relative to root (e.g. "/dummy")
        #  2. a URL relative to the current path
        # Note that any querystring will be discarded.
        path = urlparse.urljoin(cherrypy.request.path_info, path)
        
        # Set a 'path' member attribute so that code which traps this
        # error can have access to it.
        self.path = path
        
        Exception.__init__(self, path)



class HTTPRedirect(Exception):
    """Exception raised when the request should be redirected.
    
    The new URL must be passed as the first argument to the Exception, e.g.,
        cperror.HTTPRedirect(newUrl). Multiple URLs are allowed. If a URL
        is absolute, it will be used as-is. If it is relative, it is assumed
        to be relative to the current cherrypy.request.path.
    """
    
    def __init__(self, urls, status=None):
        import cherrypy
        
        if isinstance(urls, basestring):
            urls = [urls]
        
        abs_urls = []
        for url in urls:
            # Note that urljoin will "do the right thing" whether url is:
            #  1. a complete URL with host (e.g. "http://www.dummy.biz/test")
            #  2. a URL relative to root (e.g. "/dummy")
            #  3. a URL relative to the current path
            # Note that any querystring in browser_url will be discarded.
            url = urlparse.urljoin(cherrypy.request.browser_url, url)
            abs_urls.append(url)
        self.urls = abs_urls
        
        # RFC 2616 indicates a 301 response code fits our goal; however,
        # browser support for 301 is quite messy. Do 302 instead. See
        # http://ppewww.ph.gla.ac.uk/~flavell/www/post-redirect.html
        if status is None:
            if cherrypy.response.version >= "1.1":
                status = 303
            else:
                status = 302
        else:
            status = int(status)
            if status < 300 or status > 399:
                raise ValueError("status must be between 300 and 399.")
        
        self.status = status
        Exception.__init__(self, abs_urls, status)
    
    def set_response(self):
        import cherrypy
        response = cherrypy.response
        response.status = status = self.status
        
        if status in (300, 301, 302, 303, 307):
            response.headers['Content-Type'] = "text/html"
            # "The ... URI SHOULD be given by the Location field
            # in the response."
            response.headers['Location'] = self.urls[0]
            
            # "Unless the request method was HEAD, the entity of the response
            # SHOULD contain a short hypertext note with a hyperlink to the
            # new URI(s)."
            msg = {300: "This resource can be found at <a href='%s'>%s</a>.",
                   301: "This resource has permanently moved to <a href='%s'>%s</a>.",
                   302: "This resource resides temporarily at <a href='%s'>%s</a>.",
                   303: "This resource can be found at <a href='%s'>%s</a>.",
                   307: "This resource has moved temporarily to <a href='%s'>%s</a>.",
                   }[status]
            response.body = "<br />\n".join([msg % (u, u) for u in self.urls])
        elif status == 304:
            # Not Modified.
            # "The response MUST include the following header fields:
            # Date, unless its omission is required by section 14.18.1"
            # The "Date" header should have been set in Request.__init__
            
            # "The 304 response MUST NOT contain a message-body."
            response.body = None
        elif status == 305:
            # Use Proxy.
            # self.urls[0] should be the URI of the proxy.
            response.headers['Location'] = self.urls[0]
            response.body = None
        else:
            raise ValueError("The %s status code is unknown." % status)


class HTTPError(Error):
    """ Exception used to return an HTTP error code to the client.
        This exception will automatically set the response status and body.
        
        A custom message (a long description to display in the browser)
        can be provided in place of the default.
    """
    
    def __init__(self, status=500, message=None):
        self.status = status = int(status)
        if status < 400 or status > 599:
            raise ValueError("status must be between 400 and 599.")
        self.message = message
        Error.__init__(self, status, message)
    
    def set_response(self):
        """Set cherrypy.response status, headers, and body."""
        import cherrypy
        
        response = cherrypy.response
        
        # Remove headers which applied to the original content,
        # but do not apply to the error page.
        for key in ["Accept-Ranges", "Age", "ETag", "Location", "Retry-After",
                    "Vary", "Content-Encoding", "Content-Length", "Expires",
                    "Content-Location", "Content-MD5", "Last-Modified"]:
            if response.headers.has_key(key):
                del response.headers[key]
        
        if self.status != 416:
            # A server sending a response with status code 416 (Requested
            # range not satisfiable) SHOULD include a Content-Range field
            # with a byte-range- resp-spec of "*". The instance-length
            # specifies the current length of the selected resource.
            # A response with status code 206 (Partial Content) MUST NOT
            # include a Content-Range field with a byte-range- resp-spec of "*".
            if response.headers.has_key("Content-Range"):
                del response.headers["Content-Range"]
        
        # In all cases, finalize will be called after this method,
        # so don't bother cleaning up response values here.
        response.status = self.status
        tb = None
        if cherrypy.config.get('show_tracebacks', False):
            tb = format_exc()
        content = get_error_page(self.status, traceback=tb,
                                 message=self.message)
        response.body = content
        response.headers['Content-Length'] = len(content)
        response.headers['Content-Type'] = "text/html"
        
        be_ie_unfriendly(self.status)


class NotFound(HTTPError):
    """ Happens when a URL couldn't be mapped to any class.method """
    
    def __init__(self, path=None):
        if path is None:
            import cherrypy
            path = cherrypy.request.path
        self.args = (path,)
        HTTPError.__init__(self, 404, "The path %s was not found." % repr(path))


_HTTPErrorTemplate = '''<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html>
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"></meta>
    <title>%(status)s</title>
    <style type="text/css">
    #powered_by {
        margin-top: 20px;
        border-top: 2px solid black;
        font-style: italic;
    }

    #traceback {
        color: red;
    }
    </style>
</head>
    <body>
        <h2>%(status)s</h2>
        <p>%(message)s</p>
        <pre id="traceback">%(traceback)s</pre>
    <div id="powered_by">
    <span>Powered by <a href="http://www.cherrypy.org">CherryPy %(version)s</a></span>
    </div>
    </body>
</html>
'''

def get_error_page(status, **kwargs):
    """Return an HTML page, containing a pretty error response.
    
    status should be an int or a str.
    kwargs will be interpolated into the page template.
    """
    import cherrypy
    
    try:
        code, reason, message = httptools.validStatus(status)
    except ValueError, x:
        raise cherrypy.HTTPError(500, x.args[0])
    
    # We can't use setdefault here, because some
    # callers send None for kwarg values.
    if kwargs.get('status') is None:
        kwargs['status'] = "%s %s" % (code, reason)
    if kwargs.get('message') is None:
        kwargs['message'] = message
    if kwargs.get('traceback') is None:
        kwargs['traceback'] = ''
    if kwargs.get('version') is None:
        kwargs['version'] = cherrypy.__version__
    for k, v in kwargs.iteritems():
        if v is None:
            kwargs[k] = ""
        else:
            kwargs[k] = cgi.escape(kwargs[k])
    
    template = _HTTPErrorTemplate
    error_page_file = cherrypy.config.get('error_page.%s' % code, '')
    if error_page_file:
        try:
            template = file(error_page_file, 'rb').read()
        except:
            m = kwargs['message']
            if m:
                m += "<br />"
            m += ("In addition, the custom error page "
                  "failed:\n<br />%s" % (sys.exc_info()[1]))
            kwargs['message'] = m
    
    return template % kwargs


_ie_friendly_error_sizes = {
    400: 512, 403: 256, 404: 512, 405: 256,
    406: 512, 408: 512, 409: 512, 410: 256,
    500: 512, 501: 512, 505: 512,
    }


def be_ie_unfriendly(status):
    import cherrypy
    response = cherrypy.response
    
    # For some statuses, Internet Explorer 5+ shows "friendly error
    # messages" instead of our response.body if the body is smaller
    # than a given size. Fix this by returning a body over that size
    # (by adding whitespace).
    # See http://support.microsoft.com/kb/q218155/
    s = _ie_friendly_error_sizes.get(status, 0)
    if s:
        s += 1
        # Since we are issuing an HTTP error status, we assume that
        # the entity is short, and we should just collapse it.
        content = response.collapse_body()
        l = len(content)
        if l and l < s:
            # IN ADDITION: the response must be written to IE
            # in one chunk or it will still get replaced! Bah.
            content = content + (" " * (s - l))
        response.body = content
        response.headers['Content-Length'] = len(content)


def format_exc(exc=None):
    """format_exc(exc=None) -> exc (or sys.exc_info if None), formatted."""
    if exc is None:
        exc = sys.exc_info()
    if exc == (None, None, None):
        return ""
    return "".join(traceback.format_exception(*exc))

def bare_error(extrabody=None):
    """Produce status, headers, body for a critical error.
    
    Returns a triple without calling any other questionable functions,
    so it should be as error-free as possible. Call it from an HTTP server
    if you get errors outside of the request.
    
    If extrabody is None, a friendly but rather unhelpful error message
    is set in the body. If extrabody is a string, it will be appended
    as-is to the body.
    """
    
    # The whole point of this function is to be a last line-of-defense
    # in handling errors. That is, it must not raise any errors itself;
    # it cannot be allowed to fail. Therefore, don't add to it!
    # In particular, don't call any other CP functions.
    
    body = "Unrecoverable error in the server."
    if extrabody is not None:
        body += "\n" + extrabody
    
    return ("500 Internal Server Error",
            [('Content-Type', 'text/plain'),
             ('Content-Length', str(len(body)))],
            [body])

