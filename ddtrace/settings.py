from copy import deepcopy
import logging

from .pin import Pin
from .utils.merge import deepmerge
from .utils.http import normalize_header_name


log = logging.getLogger(__name__)


class ConfigException(Exception):
    """Configuration exception when an integration that is not available
    is called in the `Config` object.
    """
    pass


class Config(object):
    """Configuration object that exposes an API to set and retrieve
    global settings for each integration. All integrations must use
    this instance to register their defaults, so that they're public
    available and can be updated by users.
    """
    def __init__(self):
        # use a dict as underlying storing mechanism
        self._config = {}
        self._http = HttpConfig()

    def __getattr__(self, name):
        if name not in self._config:
            self._config[name] = IntegrationConfig(self)
        return self._config[name]

    def get_from(self, obj):
        """Retrieves the configuration for the given object.
        Any object that has an attached `Pin` must have a configuration
        and if a wrong object is given, an empty `dict` is returned
        for safety reasons.
        """
        pin = Pin.get_from(obj)
        if pin is None:
            log.debug('No configuration found for %s', obj)
            return {}

        return pin._config

    def _add(self, integration, settings, merge=True):
        """Internal API that registers an integration with given default
        settings.

        :param str integration: The integration name (i.e. `requests`)
        :param dict settings: A dictionary that contains integration settings;
            to preserve immutability of these values, the dictionary is copied
            since it contains integration defaults.
        :param bool merge: Whether to merge any existing settings with those provided,
            or if we should overwrite the settings with those provided;
            Note: when merging existing settings take precedence.
        """
        # DEV: Use `getattr()` to call our `__getattr__` helper
        existing = getattr(self, integration)
        settings = deepcopy(settings)

        if merge:
            # DEV: This may appear backwards keeping `existing` as the "source" and `settings` as
            #   the "destination", but we do not want to let `_add(..., merge=True)` overwrite any
            #   existing settings
            #
            # >>> config.requests['split_by_domain'] = True
            # >>> config._add('requests', dict(split_by_domain=False))
            # >>> config.requests['split_by_domain']
            # True
            self._config[integration] = IntegrationConfig(self, deepmerge(existing, settings))
        else:
            self._config[integration] = IntegrationConfig(self, settings)

    def trace_headers(self, whitelist):
        """
        Registers a set of headers to be traced at global level or integration level.
        :param whitelist: the case-insensitive list of traced headers
        :type whitelist: list of str or str
        :return: self
        :rtype: HttpConfig
        """
        self._http.trace_headers(whitelist)
        return self

    def header_is_traced(self, header_name):
        """
        Returns whether or not the current header should be traced.
        :param header_name: the header name
        :type header_name: str
        :rtype: bool
        """
        return self._http.header_is_traced(header_name)

    def __repr__(self):
        cls = self.__class__
        integrations = ', '.join(self._config.keys())
        return '{}.{}({})'.format(cls.__module__, cls.__name__, integrations)


class IntegrationConfig(dict):

    def __init__(self, global_config, *args, **kwargs):
        """
        :param global_config:
        :type global_config: Config
        :param args:
        :param kwargs:
        """
        super(IntegrationConfig, self).__init__(*args, **kwargs)
        self.http = HttpConfig()
        self.global_config = global_config

    def __deepcopy__(self, memodict=None):
        new = IntegrationConfig(self.global_config, deepcopy(dict(self)))
        new.http = deepcopy(self.http)
        return new

    def header_is_traced(self, header_name):
        """
        Returns whether or not the current header should be traced.
        :param header_name: the header name
        :type header_name: str
        :rtype: bool
        """
        return self.http.header_is_traced(header_name) \
            if self.http.is_header_tracing_configured \
            else self.global_config.header_is_traced(header_name)


class HttpConfig(object):
    """
    Configuration object that expose an API to set and retrieve both global and integration specific settings
    related to the http context.
    """

    def __init__(self):
        self._whitelist_headers = []

    @property
    def is_header_tracing_configured(self):
        return len(self._whitelist_headers) > 0

    def trace_headers(self, whitelist):
        """
        Registers a set of headers to be traced at global level or integration level.
        :param whitelist: the case-insensitive list of traced headers
        :type whitelist: list of str or str
        :return: self
        :rtype: HttpConfig
        """
        if not whitelist:
            return

        whitelist = [whitelist] if isinstance(whitelist, str) else whitelist
        for whitelist_entry in whitelist:
            normalized_header_name = normalize_header_name(whitelist_entry)
            if not normalized_header_name:
                continue
            self._whitelist_headers.append(normalized_header_name)

        return self

    def header_is_traced(self, header_name):
        """
        Returns whether or not the current header should be traced.
        :param header_name: the header name
        :type header_name: str
        :rtype: bool
        """
        normalized_header_name = normalize_header_name(header_name)
        log.debug('Checking header \'%s\' tracing in whitelist %s', normalized_header_name, self._whitelist_headers)
        return normalized_header_name in self._whitelist_headers

    def __repr__(self):
        return '<HttpConfig traced_headers={}>'.format(self._whitelist_headers)
