#!/usr/bin/env python

"""
This module contains the HTML extension to :class:`Table <agate.table.Table>`.
See https://github.com/pandas-dev/pandas/blob/master/pandas/io/html.py
"""

import datetime
from collections import OrderedDict

import agate
from bs4 import BeautifulSoup, SoupStrainer
import re
import six


MSO_NUMBER_FORMAT_TO_AGATE_TYPE = {
    r'0': agate.Number(),
    r'0\.0': agate.Number(),
    r'0\.00': agate.Number(),
    r'0\.000': agate.Number(),
    r'0\.0000': agate.Number(),
    r'0\.E+00': agate.Number(),
    r'0%': agate.Number(),
    r'Percent': agate.Number(),
    r'\#\ ?\/?': agate.Number(),
    r'\#\ ??\/??': agate.Number(),
    r'\#\ ???\/???': agate.Number(),
    r'Short Date': agate.Date(date_format='%d/%m/%Y'),
    r'Medium Date': agate.Date(date_format='%d-%b-%y'),
    r'Long Date': agate.Date(date_format=''),
    r'Short Time': agate.DateTime(datetime_format='%H:%M'),
    r'Medium Time': agate.DateTime(datetime_format='%I:%M %p'),
    r'Long Time': agate.DateTime(datetime_format='%H:%M:%S:%f'),
    r'\@': agate.Text(),
    # TODO add mm\/dd\/yy and so on...
}


def from_html(cls, path, table_identifier=0, header=True, encoding='utf-8', 
    mso_number_formats_override=None, row_limit=None,
    **kwargs):
    """
    Parse an HTML file.

    :param path:
        Path to an HTML file to load or a file-like object for one.
    :param table_identifier:
        The names or integer indices of the tables to load. If not specified
        then the first table will be used.
    :param header:
        If :code:`True`, the first row is assumed to contain column names.
    """

    if 'column_names' in kwargs:
        if not header:
            column_names = kwargs['column_names']
        del kwargs['column_names']

    column_types = None
    if 'column_types' in kwargs:
        column_types = kwargs['column_types']
        del kwargs['column_types']

    if 'parser' in kwargs: # TODO ignored for now
        del kwargs['parser']
    parser = 'lxml'

    if hasattr(path, 'read'):
        html_soup = BeautifulSoup(path, parser, parse_only=SoupStrainer('table'), from_encoding=encoding)
    else:
        with open(path, 'rt') as f:
            html_soup = BeautifulSoup(f.read(), parser, parse_only=SoupStrainer('table'), from_encoding=encoding)

    multiple = agate.utils.issequence(table_identifier)
    if multiple:
        table_identifiers = table_identifier
    else:
        table_identifiers = [table_identifier]

    tables = OrderedDict()

    for i, table_identifier in enumerate(table_identifiers):
        if isinstance(table_identifier, six.string_types):
#            sheet = book.sheet_by_name(sheet)
            raise Exception("Not implemented yet.") # FIXME
        elif isinstance(table_identifier, int):
            table_html = html_soup.find_all('table')[table_identifier]
        else:
            raise Exception(f"Could not interpret table identifier {table_identifier}")

        head_rows = parse_thead_tr(table_html)
        body_rows = parse_tbody_tr(table_html)
        if row_limit is not None:
            body_rows = body_rows[0:row_limit]
        foot_rows = parse_tfoot_tr(table_html)

        if not head_rows:
            # The table has no <thead>. Move the top all-<th> rows from
            # body_rows to header_rows. (This is a common case because many
            # tables in the wild have no <thead> or <tfoot>.)
            while body_rows and row_is_all_th(body_rows[0]):
                head_rows.append(body_rows.pop(0))

        head = expand_colspan_rowspan(head_rows)
        body = expand_colspan_rowspan(body_rows)
        foot = expand_colspan_rowspan(foot_rows)

        if header:
            column_names = head[0]

        tables[table_identifier] = agate.Table(rows=body, column_names=column_names, column_types=column_types, **kwargs)

    if multiple:
        return agate.MappedSequence(tables.values(), tables.keys())
    else:
        return tables.popitem()[1]


def row_is_all_th(row_html):
    return all(equals_tag(t, "th") for t in parse_td(row_html))


def attr_getter(obj, attr):
    """
    Return the attribute value of an individual DOM node.
    Parameters
    ----------
    obj : node-like
        A DOM node.
    attr : str or unicode
        The attribute, such as "colspan"
    Returns
    -------
    str or unicode
        The attribute value.
    """
    return obj.get(attr)

def text_getter(obj):
    """
    Return the text of an individual DOM node.
    Parameters
    ----------
    obj : node-like
        A DOM node.
    Returns
    -------
    text : str or unicode
        The text from an individual DOM node.
    """
    return str(obj.text)

def parse_td(row_html):
    """
    Return the td elements from a row element.
    Parameters
    ----------
    obj : node-like
        A DOM <tr> node.
    Returns
    -------
    list of node-like
        These are the elements of each row, i.e., the columns.
    """
    return row_html.find_all(("td", "th"), recursive=False)

def parse_thead_tr(table_html):
    """
    Return the list of thead row elements from the parsed table element.
    Parameters
    ----------
    table : a table element that contains zero or more thead elements.
    Returns
    -------
    list of node-like
        These are the <tr> row elements of a table.
    """
    return table_html.select("thead tr")

def parse_tbody_tr(table_html):
    """
    Return the list of tbody row elements from the parsed table element.
    HTML5 table bodies consist of either 0 or more <tbody> elements (which
    only contain <tr> elements) or 0 or more <tr> elements. This method
    checks for both structures.
    Parameters
    ----------
    table : a table element that contains row elements.
    Returns
    -------
    list of node-like
        These are the <tr> row elements of a table.
    """
    from_tbody = table_html.select("tbody tr")
    from_root = table_html.find_all("tr", recursive=False)
    # HTML spec: at most one of these lists has content
    return from_tbody + from_root

def parse_tfoot_tr(table_html):
    """
    Return the list of tfoot row elements from the parsed table element.
    Parameters
    ----------
    table : a table element that contains row elements.
    Returns
    -------
    list of node-like
        These are the <tr> row elements of a table.
    """
    return table_html.select("tfoot tr")

def equals_tag(obj, tag):
    """
    Return whether an individual DOM node matches a tag
    Parameters
    ----------
    obj : node-like
        A DOM node.
    tag : str
        Tag name to be checked for equality.
    Returns
    -------
    boolean
        Whether `obj`'s tag name is `tag`
    """
    return obj.name == tag




def expand_colspan_rowspan(rows):
    """
    Given a list of <tr>s, return a list of text rows.
    Parameters
    ----------
    rows : list of node-like
        List of <tr>s
    Returns
    -------
    list of list
        Each returned row is a list of str text.
    Notes
    -----
    Any cell with ``rowspan`` or ``colspan`` will have its contents copied
    to subsequent cells.
    """

    all_texts = []  # list of rows, each a list of str
    remainder = []  # list of (index, text, nrows)

    for tr in rows:
        texts = []  # the output for this row
        next_remainder = []

        index = 0
        tds = parse_td(tr)
        for td in tds:
            # Append texts from previous rows with rowspan>1 that come
            # before this <td>
            while remainder and remainder[0][0] <= index:
                prev_i, prev_text, prev_rowspan = remainder.pop(0)
                texts.append(prev_text)
                if prev_rowspan > 1:
                    next_remainder.append((prev_i, prev_text, prev_rowspan - 1))
                index += 1

            # Append the text from this <td>, colspan times
            text = _remove_whitespace(text_getter(td))
            rowspan = int(attr_getter(td, "rowspan") or 1)
            colspan = int(attr_getter(td, "colspan") or 1)

            for _ in range(colspan):
                texts.append(text)
                if rowspan > 1:
                    next_remainder.append((index, text, rowspan - 1))
                index += 1

        # Append texts from previous rows at the final position
        for prev_i, prev_text, prev_rowspan in remainder:
            texts.append(prev_text)
            if prev_rowspan > 1:
                next_remainder.append((prev_i, prev_text, prev_rowspan - 1))

        all_texts.append(texts)
        remainder = next_remainder

    # Append rows that only appear because the previous row had non-1
    # rowspan
    while remainder:
        next_remainder = []
        texts = []
        for prev_i, prev_text, prev_rowspan in remainder:
            texts.append(prev_text)
            if prev_rowspan > 1:
                next_remainder.append((prev_i, prev_text, prev_rowspan - 1))
        all_texts.append(texts)
        remainder = next_remainder

    return all_texts

def _handle_hidden_tables(tbl_list, attr_name, displayed_only=True):
    """
    Return list of tables, potentially removing hidden elements
    Parameters
    ----------
    tbl_list : list of node-like
        Type of list elements will vary depending upon parser used
    attr_name : str
        Name of the accessor for retrieving HTML attributes
    Returns
    -------
    list of node-like
        Return type matches `tbl_list`
    """
    if not displayed_only:
        return tbl_list
    else:
        return [
            x
            for x in tbl_list
            if "display:none"
            not in getattr(x, attr_name).get("style", "").replace(" ", "")
        ]


_RE_WHITESPACE = re.compile(r"[\r\n]+|\s{2,}")


def _remove_whitespace(s: str, regex=_RE_WHITESPACE) -> str:
    """
    Replace extra whitespace inside of a string with a single space.
    Parameters
    ----------
    s : str or unicode
        The string from which to remove extra whitespace.
    regex : re.Pattern
        The regular expression to use to remove extra whitespace.
    Returns
    -------
    subd : str or unicode
        `s` with all extra whitespace replaced with a single space.
    """
    return regex.sub(" ", s.strip())


# XLS below FIXME

def determine_agate_type(excel_type):
    try:
        return EXCEL_TO_AGATE_TYPE[excel_type]
    except KeyError:
        return agate.Text()


def determine_excel_type(types):
    """
    Determine the correct type for a column from a list of cell types.
    """
    types_set = set(types)
    types_set.discard(xlrd.biffh.XL_CELL_EMPTY)

    # Normalize mixed types to text
    if len(types_set) > 1:
        t = xlrd.biffh.XL_CELL_TEXT
        if xlrd.biffh.XL_CELL_ERROR in types_set:
            t = (t, xlrd.biffh.XL_CELL_ERROR)
    else:
        try:
            t = types_set.pop()
        except KeyError:
            t = xlrd.biffh.XL_CELL_EMPTY
    return t


def normalize_booleans(values):
    normalized = []

    for value in values:
        if value is None or value == '':
            normalized.append(None)
        else:
            normalized.append(bool(value))

    return normalized


def normalize_dates(values, datemode=0):
    """
    Normalize a column of date cells.
    """
    normalized = []
    with_date = False
    with_time = False

    for v in values:
        if not v:
            normalized.append(None)
            continue

        v_tuple = xlrd.xldate.xldate_as_datetime(v, datemode).timetuple()

        if v_tuple[3:6] == (0, 0, 0):
            # Date only
            normalized.append(datetime.date(*v_tuple[:3]))
            with_date = True
        elif v_tuple[:3] == (0, 0, 0):
            # Time only
            normalized.append(datetime.time(*v_tuple[3:6]))
            with_time = True
        else:
            # Date and time
            normalized.append(datetime.datetime(*v_tuple[:6]))
            with_date = True
            with_time = True

    return (normalized, with_date, with_time)


agate.Table.from_html = classmethod(from_html)
