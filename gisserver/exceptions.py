"""Exceptions for the WFS operations.

Not all exception codes are listed here, only the one that
apply to the current conformance class.

See:
https://docs.opengeospatial.org/is/09-025r2/09-025r2.html#35
https://docs.opengeospatial.org/is/09-025r2/09-025r2.html#411
"""
from django.utils.html import format_html


class ExternalValueError(ValueError):
    """Raise a ValueError for external input.
    This helps to distinguish between internal bugs
    (e.g. unpacking values) and misformed external input.
    """


class ExternalParsingError(ValueError):
    """Raise a ValueError for a parsing problem."""


class OWSException(Exception):
    """Base class for XML based exceptions in this module."""

    status_code = 400  # Most common code in spec
    reason = None
    service = None
    version = "2.0.0"
    code = None
    text_template = None

    def __init__(self, locator, text=None, code=None, status_code=None):
        text = text or self.text_template.format(code=self.code, locator=locator)
        super().__init__(text)
        self.locator = locator
        self.text = text
        self.code = code or self.code
        self.status_code = status_code or self.status_code

    def as_xml(self):
        return format_html(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<ows:ExceptionReport"
            ' xmlns:ows="http://www.opengis.net/ows/1.1"'
            ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
            ' xsi:schemaLocation="http://www.opengis.net/ows/1.1'
            ' http://schemas.opengis.net/ows/1.1.0/owsExceptionReport.xsd"'
            ' xml:lang="en-US"'
            ' version="2.0.0">\n'
            '  <ows:Exception exceptionCode="{code}" locator="{locator}">\n'
            "    <ows:ExceptionText>{text}</ows:ExceptionText>\n"
            "  </ows:Exception>\n"
            "</ows:ExceptionReport>",
            code=self.code,
            locator=self.locator,
            text=self.text,
        )

    def __html__(self):
        return self.as_xml()


class WFSException(OWSException):
    service = "WFS"


class OperationNotSupported(WFSException):
    """WFS Method is called, but does not exist on this server."""

    status_code = 400
    reason = "Not Implemented"
    code = "OperationNotSupported"
    text_template = "Operation is not implemented."


class OperationParsingFailed(WFSException):
    """Error parsing the request to a WFS method."""

    status_code = 400
    code = "OperationParsingFailed"
    text_template = "The request could not be parsed by the server."


class OperationProcessingFailed(WFSException):
    """Error while processing the request."""

    status_code = 500  # 400 & 403 may also be used but are deprecated.
    reason = "Server processing failed"
    code = "OperationProcessingFailed"
    text_template = "The request could not be processed by the server."


class MissingParameterValue(WFSException):
    """Required parameter is missing"""

    status_code = 400
    code = "MissingParameterValue"
    text_template = "Missing required '{locator}' parameter."


class InvalidParameterValue(WFSException):
    """Unsupported choice, e.g. unsupported CRS, bad resultType."""

    status_code = 400
    code = "InvalidParameterValue"
    text_template = "Invalid value for '{locator}' parameter."


class VersionNegotiationFailed(WFSException):
    """GetCapabilities called with unsupported versions."""

    status_code = 400
    code = "VersionNegotiationFailed"
    text_template = "'ACCEPTVERSIONS' contains an invalid version number."


class NotFound(WFSException):
    """The requested ResourceId could not be found."""

    status_code = 404
    reason = "Invalid feature or property value"
    code = "NotFound"
    text_template = "Invalid feature or property value"


class OptionNotSupported(WFSException):
    status_code = 400
    reason = "Not Implemented"
    code = "OptionNotSupported"
    text_template = "Option is not implemented."


class PermissionDenied(WFSException):
    """Permission denied (custom error).

    Note this error is not part of the spec,
    but it's still useful to have access controls.
    """

    status_code = 403
    reason = "Permission Denied"
    code = "PermissionDenied"
    text_template = "You do not have permission to perform this action."
