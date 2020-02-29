# Copyright (c) Mykola Grechukh <mgrechukh@satelliz.com>

# partially based on work from https://gist.github.com/fmoo/2018384 by Peter Ruibal

""" HTTP CONNECT support
"""

from twisted.internet import defer, interfaces
from zope.interface import implementer
from twisted.web import http

from .client import _SOCKSClientFactory
from .errors import ConnectionError


class HTTPConnectClient(http.HTTPClient):
    """HTTPClient protocol to send a CONNECT message for proxies.
    """

    def __init__(self):
        self.sender = self

    def connectionMade(self):
        self.sendCommand('CONNECT', '%s:%d' %
                         (self.factory.host, self.factory.port))
        self.endHeaders()

    def handleStatus(self, version, status, message):
        if str(status) != "200":
            raise ConnectionError("Unexpected status on CONNECT: %s" % status)

    def handleEndHeaders(self):
        self.factory.proxyConnectionEstablished(self)

    def proxyEstablished(self, other):
        self.otherProtocol = other
        other.makeConnection(self.sender.transport)

        # a bit rude, but a huge performance increase
        if hasattr(self.sender.transport, 'protocol'):
            self.sender.transport.protocol = other


class HTTPConnectClientFactory(_SOCKSClientFactory):
    protocol = HTTPConnectClient

    def __init__(self, host, port, proxiedFactory):
        self.host = host
        self.port = port
        self.proxiedFactory = proxiedFactory
        self.deferred = defer.Deferred(self._cancel)


@implementer(interfaces.IStreamClientEndpoint)
class HTTPConnectClientEndpoint(object):
    """An endpoint which does HTTP CONNECT negotiation.

    :param host: The hostname to connect to through the proxy server. This
        will not be resolved by ``txsocksx`` but will be sent without
        modification to the proxy server to be resolved remotely.
    :param port: The port to connect to through the proxy server.
    :param proxyEndpoint: The endpoint of the proxy server. This must provide
        `IStreamClientEndpoint`__.

    __ http://twistedmatrix.com/documents/current/api/twisted.internet.interfaces.IStreamClientEndpoint.html

    """

    def __init__(self, host, port, proxyEndpoint):
        self.host = host
        self.port = port
        self.proxyEndpoint = proxyEndpoint

    def connect(self, fac):
        """Connect over proxy with HTTP CONNECT

        The provided factory will have its ``buildProtocol`` method once a
        HTTP CONNECT connection has been successfully negotiated. Returns a
        ``Deferred`` which will fire with the resulting ``Protocol`` when
        negotiation finishes, or errback for a variety of reasons. For example:

        1. If the ``Deferred`` returned by ``proxyEndpoint.connect`` errbacks
           (e.g. the connection to the proxy server was refused).
        2. If the proxy server gave a non-success response.
        3. If the ``Deferred`` returned from ``connect`` was cancelled.

        The returned ``Deferred`` is cancelable during negotiation: the
        connection will immediately close and the ``Deferred`` will errback
        with a ``CancelledError``. The ``Deferred`` can be canceled before
        negotiation starts only if the ``Deferred`` returned by
        ``proxyEndpoint.connect`` is cancelable.

        If the factory's ``buildProtocol`` returns ``None``, the connection
        will immediately close.

        """

        proxyFac = HTTPConnectClientFactory(self.host, self.port, fac)
        d = self.proxyEndpoint.connect(proxyFac)
        d.addCallback(lambda proto: proxyFac.deferred)
        return d
