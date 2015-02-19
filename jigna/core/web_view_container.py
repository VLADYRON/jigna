#
# Jigna product code
#
# (C) Copyright 2013 Enthought, Inc., Austin, TX
# All right reserved.
#

# Standard library imports.
import sys
import webbrowser
import logging
from types import NoneType

# Enthought library imports.
from traits.api import ( HasTraits, Any, Bool, Callable, Dict, Either,
    List, Property, Str, Tuple, Unicode, on_trait_change, Float )

# Local imports.
from jigna.core.interoperation import create_js_object_wrapper
from jigna.core.network_access import ProxyAccessManager
from jigna.qt import QtCore, QtGui, QtWebKit

logger = logging.getLogger(__name__)


class JignaWebView(QtWebKit.QWebView):

    DISABLED_ACTIONS = [
        QtWebKit.QWebPage.OpenLinkInNewWindow,
        QtWebKit.QWebPage.DownloadLinkToDisk,
        QtWebKit.QWebPage.OpenImageInNewWindow,
        QtWebKit.QWebPage.OpenFrameInNewWindow,
        QtWebKit.QWebPage.DownloadImageToDisk
    ]

    def __init__(
        self, parent=None, python_namespace=None, callbacks=[], debug=True,
        root_paths={}
    ):
        super(JignaWebView, self).__init__(parent)

        # Connect JS with python.
        self.expose_python_namespace(python_namespace, callbacks)

        # Install custom access manager to handle '/jigna' requests.
        access_manager = ProxyAccessManager(root_paths=root_paths)
        self.page().setNetworkAccessManager(access_manager)

        # Disable some actions
        for action in self.DISABLED_ACTIONS:
            self.pageAction(action).setVisible(False)

        # Setup debug flag
        self.page().settings().setAttribute(
            QtWebKit.QWebSettings.DeveloperExtrasEnabled, debug
        )

        # Set sizing policy
        self.setSizePolicy(
            QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding
        )

    def execute_js(self, js):
        """ Execute JavaScript synchronously.

        Warning: under most circumstances, this method should not be called when
        the page is loading.
        """
        frame = self.page().mainFrame()
        result = frame.evaluateJavaScript(js)
        result = self._apply_null_fix(result)

        return result

    def expose_python_namespace(self, python_namespace, callbacks):
        """
        Exposes the given python namespace to Javascript, using which Javascript
        can access the given list of callbacks as if they were methods on the
        object described by the python namespace.

        python_namespace: str:
            Namespace to expose to the JS world. This creates an object of the
            same name and attaches it to window frame.

        callbacks: [method_name: callable]:
            This list of callbacks is what is exposed to the JS world via the
            given python namespace.

        Usage:
        ------

        For example, doing this::

            expose_python_namespace('python', ['say_hello', say_hello])

        will create a window level object on the JS side which looks like this::

            window.python.say_hello == <a function which calls Python land>

        """
        frame = self.page().mainFrame()
        js_wrapper = create_js_object_wrapper(callbacks=callbacks, parent=frame)
        frame.javaScriptWindowObjectCleared.connect(
            lambda: frame.addToJavaScriptWindowObject(
                python_namespace, js_wrapper
            )
        )

    #### Private protocol #####################################################

    def _apply_null_fix(self, obj):
        """ Makes sure that None objects coming from Qt bridge are actually None.

        We need this because NoneType objects coming from PyQt are of a
        `QPyNullVariant` type, not None. This method converts such objects to
        the standard None type.
        """
        if isinstance(obj, getattr(QtCore, 'QPyNullVariant', NoneType)):
            return None

        return obj

class WebViewContainer(HasTraits):
    """ A container for displaying web content.

    """

    control = Any

    parent = Any

    # The URL for the current page. Read only.
    url = Str

    # Whether the page is currently loading.
    loading = Bool(False)

    # The title of the current web page.
    title = Unicode

    # Should links be opened in an external browser? Note that any custom URL
    # handling takes precedence over this option.
    open_externally = Bool(False)

    # The zoom level of the page
    zoom = Property(Float)

    # Whether debugging tools are enabled in the web view.
    debug = Bool(False)

    nav_bar = Bool(True)

    #### Python-JavaScript interoperation #####################################

    # A list of callables to expose to Javascript. Each pair is either a method
    # name or a tuple of form:
    #
    #     (javascript_name, callable(arg1, arg2, ...) -> result).
    #
    # Only primitive values (bool, int, long, float, str, and unicode) are
    # supported as arguments and return values. Keyword arguments and
    # variable-length argument lists are ignored.
    callbacks = List(Either(Str, Tuple(Str, Callable)))

    # The name of the Javascript object that will contain the registered
    # callbacks and properties.
    python_namespace = Str('python')

    # A list of schemes to intercept clicks on and functions to handle
    # them, e.g.
    #
    #     ('doc', foo.open_doc)
    #
    # The callback should take a URL and handle opening or loading.
    click_schemes = Dict(Str, Callable)

    # A list of hosts and wsgi apps to handle them
    # (http://www.python.org/dev/peps/pep-3333/), e.g.,
    #
    #     ('doc.jigna', doc_url_to_html)
    #
    # The callback should take a URL and return an HTML string.
    hosts = Dict(Str, Callable)

    # A list of url root paths and wsgi apps to handle them.
    root_paths = Dict(Str, Callable)

    #### Private interface ####################################################

    _network_access = Any

    # The exposed `PythonContainer` qobjects exposed to javascript in the
    # main frame. This list is maintained to delete the object when
    # it is no longer referenced.
    _exposed_containers = List

    # The disabled actions on the page
    _disabled_actions = List

    ###########################################################################
    # 'IWidget' interface.
    ###########################################################################

    def _create_control(self, parent):
        """ Create and return the toolkit-specific control for the widget.
        """
        # Create control.
        _WebView = (
            DarwinWebView if sys.platform == 'darwin' else QtWebKit.QWebView
        )
        control = _WebView(parent)
        control.setSizePolicy(QtGui.QSizePolicy.Expanding,
                              QtGui.QSizePolicy.Expanding)
        page = QtWebKit.QWebPage(control)
        control.setPage(page)
        frame = page.mainFrame()

        # Connect signals.
        frame.javaScriptWindowObjectCleared.connect(self._js_cleared_signal)
        frame.titleChanged.connect(self._title_signal)
        frame.urlChanged.connect(self._url_signal)
        page.loadFinished.connect(self._load_finished_signal)

        for action in self._disabled_actions:
            control.pageAction(action).setVisible(False)

        # Install the access manager.
        self._network_access = ProxyAccessManager(root_paths=self.root_paths,
                                                  hosts=self.hosts)
        self._network_access.inject(control)

        if hasattr(self, '_zoom'):
            # _zoom attribute is set by _set_zoom() if zoom property is set
            # before the control is created
            self.zoom = self._zoom
            del self._zoom

        return control

    def destroy(self):
        """ Destroy the control, if it exists.
        """
        # Stop loading and call the page's deleteLater(). Setting the
        # page to None cause crazy crashes and perhaps memory corruption.
        self.control.stop()
        self.control.close()
        self._network_access.deleteLater()
        self.control.page().deleteLater()

        if self.control is not None:
            self.control.hide()
            self.control.deleteLater()
            self.control = None

    def create(self, parent=None):
        """ Create the HTML widget's underlying control.

        The HTML widget should be torn down by calling ``destroy()``, which is
        part of the IWidget interface.
        """
        self.parent = parent
        self.control = self._create_control(parent)

    def execute_js(self, js):
        """ Execute JavaScript synchronously.

        Warning: under most circumstances, this method should not be called when
        the page is loading.
        """
        frame = self.control.page().mainFrame()
        result = frame.evaluateJavaScript(js)
        result = self._apply_null_fix(result)

        return result

    def load_html(self, html, base_url=None):
        """ Loads raw HTML into the widget.

        Parameters:
        -----------
        html : unicode
            An HTML string.

        base_url : str
            If specified, external objects (e.g. stylesheets and images) are
            relative to this URL.
        """
        self.loading = True
        if base_url:
            url = base_url
            if not url.endswith('/'):
                url += '/'
            self.control.setHtml(html, QtCore.QUrl.fromLocalFile(url))
        else:
            self.control.setHtml(html)
        self.url = ''

    def load_url(self, url):
        """ Loads the given URL.
        """
        self.loading = True
        self.control.load(QtCore.QUrl(url))
        self.url = url

    #### Navigation ###########################################################

    def back(self):
        """ Navigate backward in history.
        """
        self.control.back()

    def forward(self):
        """ Navigate forward in history.
        """
        self.control.forward()

    def reload(self):
        """ Reload the current web page.
        """
        self.control.reload()

    def stop(self):
        """ Stop loading the curent web page.
        """
        self.control.stop()

    #### Generic GUI methods ##################################################

    def undo(self):
        """ Performs an undo action in the underlying widget.
        """
        self.control.page().triggerAction(QtWebKit.QWebPage.Undo)

    def redo(self):
        """ Performs a redo action in the underlying widget.
        """
        self.control.page().triggerAction(QtWebKit.QWebPage.Redo)

    def cut(self):
        """ Performs a cut action in the underlying widget.
        """
        self.control.page().triggerAction(QtWebKit.QWebPage.Cut)

    def copy(self):
        """ Performs a copy action in the underlying widget.
        """
        self.control.page().triggerAction(QtWebKit.QWebPage.Copy)

    def paste(self):
        """ Performs a paste action in the underlying widget.
        """
        self.control.page().triggerAction(QtWebKit.QWebPage.Paste)

    def select_all(self):
        """ Performs a select all action in the underlying widget.
        """
        self.control.page().triggerAction(QtWebKit.QWebPage.SelectAll)

    ###########################################################################
    # Private interface.
    ###########################################################################

    #### Trait change handlers ################################################

    @on_trait_change('control, debug')
    def _update_debug(self):
        if self.control:
            page = self.control.page()
            page.settings().setAttribute(
                QtWebKit.QWebSettings.DeveloperExtrasEnabled, self.debug)

    @on_trait_change('hosts')
    def _update_network_access(self):
        if self._network_access:
            self._network_access.hosts = self.hosts

    #### Trait property getters/setters #######################################

    def _get_zoom(self):
        if self.control is not None:
            return self.control.zoomFactor()
        else:
            return 1.0

    def _set_zoom(self, zoom):
        if self.control is not None:
            self.control.setZoomFactor(zoom)
        else:
            self._zoom = zoom

    #### Trait initializers ###################################################

    def __disabled_actions_default(self):
        return [QtWebKit.QWebPage.OpenLinkInNewWindow,
                QtWebKit.QWebPage.DownloadLinkToDisk,
                QtWebKit.QWebPage.OpenImageInNewWindow,
                QtWebKit.QWebPage.OpenFrameInNewWindow,
                QtWebKit.QWebPage.DownloadImageToDisk]

    #### Signal handlers ######################################################

    def _js_cleared_signal(self):
        if self.control is not None:
            frame = self.control.page().mainFrame()

            # Since the js `window` object is cleared by the frame which still
            # exists, we need to explicitly delete the exposed objects.
            for exposed_obj in self._exposed_containers:
                exposed_obj.deleteLater()

            self._exposed_containers = exposed_containers = []

            if self.callbacks:
                js_object_wrapper = create_js_object_wrapper(
                    callbacks=self.callbacks
                )

                frame.addToJavaScriptWindowObject(
                    self.python_namespace, js_object_wrapper
                )

                exposed_containers.append(js_object_wrapper)

    def _load_finished_signal(self, ok):
        # Make sure that the widget has not been destroyed during loading.
        if self.control is not None:
            self.loading = False

    def _title_signal(self, title):
        self.title = title

    def _url_signal(self, url):
        self.url = url.toString()

    def _apply_null_fix(self, obj):
        """ Makes sure that None objects coming from Qt bridge are actually None.

        We need this because NoneType objects coming from PyQt are of a
        `QPyNullVariant` type, not None. This method converts such objects to
        the standard None type.
        """
        if isinstance(obj, getattr(QtCore, 'QPyNullVariant', NoneType)):
            return None

        return obj

    def default_context_menu(self):
        """ Return the default context menu. """
        if self.control is None:
            return None

        page = self.control.page()
        qmenu = page.createStandardContextMenu()
        return qmenu


class DarwinWebView(QtWebKit.QWebView):
    """ A QWebView suitable for use in HTMLWidget. """

    def __init__(self, parent):
        super(DarwinWebView, self).__init__(parent)
        self.wheel_timer = QtCore.QTimer()
        self.wheel_timer.setSingleShot(True)
        self.wheel_timer.setInterval(25)
        self.wheel_timer.timeout.connect(self._emit_wheel_event)
        self.wheel_accumulator = 0
        self._saved_wheel_event_info = ()

    def fix_key_event(self, event):
        """ Swap Ctrl and Meta on OS X.

        By default, Qt on OS X maps Command to Qt::CTRL and Control to Qt::META
        to make cross-platform keyboard shortcuts convenient. Unfortunataely,
        QWebView adopts this behavior, which makes (for example) jQuery's
        ctrlDown event correspond to Command. This behavior is wrong: on both
        Chrome and Safari, ctrlDown corresponds to Control, not Command.

        NOTE: This is not being used. Kept for posterity in case someone
        can find a way to split the browser page key events from native events.

        NOTE: Swapping is disabled for now: Command key down event for
        Control in browser is more acceptable than changing the Copy/Paste
        shortcuts to be Ctrl+C/Ctrl+V on Mac instead of Cmd+C/Cmd+V,
        which is the cause of a few user bug reports.

        """
        darwin_swapped = not QtCore.QCoreApplication.testAttribute(
            QtCore.Qt.AA_MacDontSwapCtrlAndMeta)

        if darwin_swapped:
            key = event.key()
            if key == QtCore.Qt.Key_Control:
                key = QtCore.Qt.Key_Meta
            elif key == QtCore.Qt.Key_Meta:
                key = QtCore.Qt.Key_Control

            modifiers = event.modifiers() \
                & ~QtCore.Qt.ControlModifier & ~QtCore.Qt.MetaModifier
            if event.modifiers() & QtCore.Qt.ControlModifier:
                modifiers |= QtCore.Qt.MetaModifier
            if event.modifiers() & QtCore.Qt.MetaModifier:
                modifiers |= QtCore.Qt.ControlModifier

            return QtGui.QKeyEvent(event.type(), key, modifiers, event.text(),
                                   event.isAutoRepeat(), event.count())

        return event

    def wheelEvent(self, event):
        """ Reimplemented to work around scrolling bug in Mac.

        Work around https://bugreports.qt-project.org/browse/QTBUG-22269.
        Accumulate wheel events that are within a period of 25ms into a single
        event.  Changes in buttons or modifiers, while a scroll is going on,
        are not handled, since they seem to be too much of a corner case to be
        worth handling.
        """

        self.wheel_accumulator += event.delta()
        self._saved_wheel_event_info = (
                                        event.pos(),
                                        event.globalPos(),
                                        self.wheel_accumulator,
                                        event.buttons(),
                                        event.modifiers(),
                                        event.orientation()
                                    )
        event.setAccepted(True)

        if not self.wheel_timer.isActive():
            self.wheel_timer.start()

    def _emit_wheel_event(self):
        event = QtGui.QWheelEvent(*self._saved_wheel_event_info)
        super(WebView, self).wheelEvent(event)
        self.wheel_timer.stop()
        self.wheel_accumulator = 0


if __name__ == '__main__':
    from jigna.qt import QtGui
    app = QtGui.QApplication.instance() or QtGui.QApplication([])
    w = HTMLWidget()
    w.create()
    w.control.show()
    w.load_url('http://www.google.com/')
    app.exec_()
