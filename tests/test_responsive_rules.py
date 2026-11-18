"""Regresiones de tamaños lógicos sin necesidad de Qt ni pantalla."""
from ui.responsive_rules import layout_metrics, media_columns
from core.workspaces import WORKSPACES, WORKSPACE_STATE_VERSION


def test_breakpoints_are_stable():
    for width, height, expected in ((1024, 768, 'compact'),
                                    (1366, 768, 'standard'),
                                    (1920, 1080, 'wide'),
                                    (2560, 1440, 'wide')):
        metrics = layout_metrics(width, height)
        assert metrics.tier == expected
        assert metrics.left + metrics.right < width
        assert width - metrics.left - metrics.right >= 300
        assert 190 <= metrics.timeline_height <= 480


def test_monitor_gets_priority_over_sidebars():
    for width in (800, 900, 1024, 1280, 1440, 1920, 2560):
        m = layout_metrics(width, 900)
        assert m.left + m.right + 300 <= width


def test_cards_change_with_width():
    assert media_columns(210) == 1
    assert media_columns(320) == 2
    assert media_columns(510) == 3


def test_both_workspaces_have_all_required_panels():
    assert WORKSPACE_STATE_VERSION >= 3
    for spec in WORKSPACES.values():
        included = {spec.left_top, spec.left_bottom, spec.right_top,
                    spec.right_bottom, spec.right_extra, spec.bottom_left,
                    spec.bottom_main}
        for name in ('Proyecto', 'Herramientas', 'Timeline', 'Audio Meter',
                     'Efectos (futuro)', 'Propiedades'):
            assert name in included
            assert name not in spec.hidden


def test_responsive_only_changes_visual_settings_not_timeline_scale():
    import inspect
    from ui import responsive_rules
    assert 'scale' not in inspect.getsource(responsive_rules.layout_metrics)
