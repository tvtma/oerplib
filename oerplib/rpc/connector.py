# -*- coding: UTF-8 -*-
"""Provides the ``ConnectorXMLRPC`` and ``ConnectorNetRPC`` classes."""

import xmlrpclib, socket
import abc
import time

from oerplib.rpc import error, socket_netrpc


class Connector(object):
    """Connector base class defining the interface used
    to interact with an OpenERP server.
    """
    __metaclass__ = abc.ABCMeta

    def __init__(self, server, port):
        self.server = server
        try:
            int(port)
        except ValueError:
            txt = "The port '{0}' is invalid. An integer is required."
            txt = error.format(port)
            raise error.ConnectorError(txt)
        else:
            self.port = port

    @abc.abstractmethod
    def _request(self, service, method, *args):
        """Execute the given `method` on the `service` supplied."""
        pass

    @abc.abstractmethod
    def login(self, database, user, passwd):
        """Log in the user on a database. Return the user's ID.
        Raise a LoginError exception if an error occur.
        """
        pass

    @abc.abstractmethod
    def execute(self, uid, upasswd, osv_name, method, *args):
        """Execute a simple RPC query. Return the result of
        the remote procedure.
        Raise a ExecuteError exception if an error occur.
        """
        pass

    @abc.abstractmethod
    def exec_workflow(self, uid, upasswd, osv_name, signal, obj_id):
        """Execute a RPC workflow query.
        Raise a ExecWorkflowError exception if an error occur.
        """
        pass

    @abc.abstractmethod
    def report(self, uid, upasswd, report_name,
               osv_name, obj_id, report_type='pdf', context=None):
        """Execute a RPC query to retrieve a report.
        'report_type' can be 'pdf', 'webkit', etc.
        Raise a ExecReportError exception if an error occur.
        """
        pass


class ConnectorXMLRPC(Connector):
    """Connector class using XMLRPC protocol."""
    def __init__(self, server, port):
        super(ConnectorXMLRPC, self).__init__(server, port)
        self._url = 'http://{server}:{port}/xmlrpc'.format(server=self.server,
                                                          port=self.port)

    def __getattr__(self, name):
        #TODO: instanciate on the fly resource objects (common, object, ...)
        pass

    def _request(self, service, method, *args):
        service_url = self._url + '/' + service
        sock = xmlrpclib.ServerProxy(service_url, allow_none=True)
        sock_method = getattr(sock, method, False)
        return sock_method(*args)

    def login(self, database, user, passwd):
        self.database = database
        try:
            user_id = self._request('common', 'login',
                                    self.database, user, passwd)
        except xmlrpclib.Fault as exc:
            #NOTE: exc.faultCode is in unicode and Exception doesn't
            # handle unicode object
            raise error.LoginError(repr(exc.faultCode))
        except socket.error as exc:
            raise error.LoginError(exc.strerror)
        else:
            return user_id

    def execute(self, uid, upasswd, osv_name, method, *args):
        try:
            return self._request('object', 'execute',
                                 self.database, uid, upasswd,
                                 osv_name, method, *args)
        except socket.error as exc:
            raise error.ExecuteError(exc.strerror)
        except xmlrpclib.Fault as exc:
            raise error.ExecuteError(exc.faultCode)
        except xmlrpclib.Error as exc:
            raise error.ExecuteError("{0}: {1}".format(
                                            exc.faultCode or "Unknown error",
                                            exc.faultString))

    def exec_workflow(self, uid, upasswd, osv_name, signal, obj_id):
        try:
            return self._request('object', 'exec_workflow',
                                 self.database, uid, upasswd,
                                 osv_name, signal, obj_id)
        except Exception:
            raise error.ExecWorkflowError("Workflow query has failed.")

    def report(self, uid, upasswd, report_name,
               osv_name, obj_id, report_type='pdf', context=None):
        if context is None:
            context = {}
        data = {'model': osv_name, 'id': obj_id, 'report_type': report_type}
        try:
            report_id = self._request('report', 'report',
                                      self.database, uid, upasswd,
                                      report_name, [obj_id], data, context)
        except xmlrpclib.Error as exc:
            raise error.ExecReportError(exc.faultCode)
        state = False
        attempt = 0
        while not state:
            try:
                pdf_data = self._request('report', 'report_get',
                                         self.database, uid, upasswd, report_id)
            except xmlrpclib.Error as exc:
                raise error.ExecReportError("Unknown error occurred during the "
                                      "download of the report.")
            state = pdf_data['state']
            if not state:
                time.sleep(1)
                attempt += 1
            if attempt > 200:
                raise error.ExecReportError("Download time exceeded, "
                                      "the operation has been canceled.")
        return pdf_data


class ConnectorNetRPC(Connector):
    """Connector class using NetRPC protocol."""
    def __init__(self, server, port):
        super(ConnectorNetRPC, self).__init__(server, port)

    def _request(self, service, method, *args):
        self.sock = socket_netrpc.NetRPC()
        self.sock.connect(self.server, self.port)
        self.sock.send((service, method, )+args)
        result = self.sock.receive()
        self.sock.disconnect()
        return result

    def login(self, database, user, passwd):
        self.database = database
        try:
            return self._request('common', 'login',
                                 self.database, user, passwd)
        except socket_netrpc.NetRPCError as exc:
            raise error.LoginError(unicode(exc))

    def execute(self, uid, upasswd, osv_name, method, *args):
        try:
            return self._request('object', 'execute', self.database,
                                 uid, upasswd, osv_name, method, *args)
        except socket_netrpc.NetRPCError as exc:
            raise error.ExecuteError(unicode(exc))

    def exec_workflow(self, uid, upasswd, osv_name, signal, obj_id):
        try:
            return self._request('object', 'exec_workflow', self.database,
                                 uid, upasswd, osv_name, signal, obj_id)
        except socket_netrpc.NetRPCError as exc:
            raise error.ExecWorkflowError("Workflow query has failed.")

    def report(self, uid, upasswd, report_name,
               osv_name, obj_id, report_type='pdf', context=None):
        if context is None:
            context = {}
        data = {'model': osv_name, 'id': obj_id, 'report_type': report_type}
        try:
            report_id = self._request('report', 'report', self.database,
                                      uid, upasswd, report_name, [obj_id],
                                      data, context)
        except socket_netrpc.NetRPCError as exc:
            raise error.ExecReportError(unicode(exc))
        state = False
        attempt = 0
        while not state:
            try:
                pdf_data = self._request('report', 'report_get', self.database,
                                         uid, upasswd, report_id)
            except socket_netrpc.NetRPCError as exc:
                raise error.ExecReportError("Unknown error occurred during the "
                                      "download of the report.")
            state = pdf_data['state']
            if not state:
                time.sleep(1)
                attempt += 1
            if attempt > 200:
                raise error.ExecReportError(
                        "Download time exceeded, "
                        "the operation has been canceled.")
        return pdf_data

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
