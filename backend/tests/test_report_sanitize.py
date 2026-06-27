"""Unit tests for the Report rich-text sanitizer (PRD #632, slice #634).

This is the security boundary for report free-text: it must keep the tiny allowlist
and strip everything else. These tests assert external behaviour (what survives /
what is removed), not nh3 internals.
"""
from incidents.services.report_sanitize import sanitize_report_richtext as clean


def test_allowlisted_tags_survive():
    src = "<p>hi <strong>b</strong> <em>i</em> <u>u</u></p><ul><li>a</li></ul><ol><li>n</li></ol>"
    out = clean(src)
    for tag in ("<p>", "<strong>", "<em>", "<u>", "<ul>", "<ol>", "<li>"):
        assert tag in out
    assert "hi" in out and "a" in out


def test_br_survives():
    assert "<br>" in clean("line<br>break")


def test_script_tag_and_content_removed():
    out = clean("<script>alert(1)</script><p>safe</p>")
    assert "script" not in out.lower()
    assert "alert(1)" not in out
    assert "<p>safe</p>" in out


def test_event_handler_attributes_stripped():
    out = clean('<p onclick="evil()">x</p>')
    assert "onclick" not in out
    assert "evil" not in out
    assert "<p>x</p>" == out


def test_style_attribute_stripped():
    out = clean('<p style="margin-left:9999px">x</p>')
    assert "style" not in out
    assert "<p>x</p>" == out


def test_links_and_images_removed_text_kept():
    out = clean('<a href="javascript:alert(1)">click</a><img src=x onerror=boom>tail')
    assert "<a" not in out and "href" not in out
    assert "<img" not in out and "onerror" not in out
    assert "javascript" not in out
    assert "click" in out and "tail" in out


def test_disallowed_tags_removed_but_text_preserved():
    out = clean("<h1>Title</h1><table><tr><td>cell</td></tr></table><div>d</div>")
    assert "<h1>" not in out and "<table>" not in out and "<div>" not in out
    assert "Title" in out and "cell" in out and "d" in out


def test_only_indent_classes_permitted():
    out = clean('<p class="indent-2 utility-leak">x</p>')
    assert 'class="indent-2"' in out
    assert "utility-leak" not in out


def test_non_indent_class_dropped_entirely():
    out = clean('<p class="foo bar">y</p>')
    assert "class" not in out
    assert "<p>y</p>" == out


def test_indent_classes_within_cap():
    for ok in ("indent-1", "indent-2", "indent-3"):
        assert f'class="{ok}"' in clean(f'<li class="{ok}">x</li>')
    # out-of-range indent is dropped (cap is 3)
    assert "class" not in clean('<li class="indent-9">x</li>')


def test_class_only_allowed_on_p_and_li():
    # strong is allowlisted but carries no attributes
    out = clean('<strong class="indent-1">x</strong>')
    assert "class" not in out
    assert "<strong>x</strong>" == out


def test_idempotent():
    src = '<p class="indent-1"><strong>x</strong></p><ul><li>y</li></ul>'
    once = clean(src)
    assert clean(once) == once


def test_empty_and_none_safe():
    assert clean("") == ""
    assert clean(None) == ""
    assert clean("   plain text   ").strip() == "plain text"
