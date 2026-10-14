#!/usr/bin/env python3
"""Build the TouchOSC layout that replaces Uno + MPU6050 + DRV2605."""

from __future__ import annotations

import uuid
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LUA = (ROOT / "touchosc" / "HearTheUnseen.lua").read_text(encoding="utf-8")
BUTTON_LUA = """function onValueChanged(key)
  if key == 'x' and self.values.x > 0 then
    vibrate()
    sendOSC('/ping', getMillis())
  end
end
"""


def uid() -> str:
    return str(uuid.uuid4())


def cdata(text: str) -> str:
    return f"<![CDATA[{text}]]>"


def property_xml(kind: str, key: str, body: str) -> str:
    return f"<property type='{kind}'><key>{cdata(key)}</key>{body}</property>"


def string_prop(key: str, value: str) -> str:
    return property_xml("s", key, f"<value>{cdata(value)}</value>")


def bool_prop(key: str, value: bool) -> str:
    return property_xml("b", key, f"<value>{1 if value else 0}</value>")


def int_prop(key: str, value: int) -> str:
    return property_xml("i", key, f"<value>{value}</value>")


def frame_prop(x: int, y: int, w: int, h: int) -> str:
    return property_xml("r", "frame", f"<value><x>{x}</x><y>{y}</y><w>{w}</w><h>{h}</h></value>")


def color_prop(key: str, r: float, g: float, b: float, a: float = 1.0) -> str:
    def n(value: float) -> str:
        return str(int(value)) if float(value).is_integer() else str(value)

    return property_xml("c", key, f"<value><r>{n(r)}</r><g>{n(g)}</g><b>{n(b)}</b><a>{n(a)}</a></value>")


def value_xml(key: str, default: str) -> str:
    return (
        "<value>"
        f"<key>{cdata(key)}</key>"
        "<locked>0</locked><lockedDefaultCurrent>0</lockedDefaultCurrent>"
        f"<default>{cdata(default)}</default><defaultPull>0</defaultPull>"
        "</value>"
    )


def common_props(
    *,
    name: str,
    frame: tuple[int, int, int, int],
    color: tuple[float, float, float, float],
    interactive: bool,
    grab_focus: bool,
    outline_style: int,
    script: str | None = None,
    extra: str = "",
) -> str:
    parts = [
        bool_prop("background", True),
        color_prop("color", *color),
        int_prop("cornerRadius", 0),
        frame_prop(*frame),
        bool_prop("grabFocus", grab_focus),
        bool_prop("interactive", interactive),
        bool_prop("locked", False),
        string_prop("name", name),
        int_prop("orientation", 0),
        bool_prop("outline", True),
        int_prop("outlineStyle", outline_style),
        int_prop("pointerPriority", 0),
        int_prop("shape", 1),
        bool_prop("visible", True),
    ]
    if script:
        parts.append(string_prop("script", script))
    xml = "".join(sorted(parts, key=lambda item: item.split("<key>")[1]))
    return xml + extra


def label(*, name: str, text: str, frame: tuple[int, int, int, int], size: int, color: tuple[float, float, float, float]) -> str:
    props = common_props(
        name=name,
        frame=frame,
        color=color,
        interactive=False,
        grab_focus=True,
        outline_style=1,
        extra=(
            int_prop("font", 0)
            + int_prop("textAlignH", 2)
            + int_prop("textAlignV", 2)
            + bool_prop("textClip", True)
            + color_prop("textColor", 0.85, 0.95, 1.0, 1.0)
            + int_prop("textLength", 0)
            + int_prop("textSize", size)
        ),
    )
    return (
        f"<node ID='{uid()}' type='LABEL'><properties>{props}</properties>"
        f"<values>{value_xml('text', text)}{value_xml('touch', 'false')}</values></node>"
    )


def button(*, name: str, frame: tuple[int, int, int, int], script: str) -> str:
    props = common_props(
        name=name,
        frame=frame,
        color=(0.16, 0.72, 0.92, 1.0),
        interactive=True,
        grab_focus=True,
        outline_style=1,
        script=script,
        extra=int_prop("buttonType", 0) + bool_prop("press", True) + bool_prop("release", True) + bool_prop("valuePosition", False),
    )
    return (
        f"<node ID='{uid()}' type='BUTTON'><properties>{props}</properties>"
        f"<values>{value_xml('x', '0')}{value_xml('touch', 'false')}</values></node>"
    )


def build_xml() -> str:
    children = "".join(
        [
            label(name="title", text="Hear the Unseen", frame=(40, 80, 670, 90), size=36, color=(0.07, 0.14, 0.22, 1.0)),
            label(name="subtitle", text="iPhone IMU + Taptic", frame=(40, 170, 670, 48), size=20, color=(0.07, 0.14, 0.22, 1.0)),
            label(name="omega", text="— °/s", frame=(40, 280, 670, 160), size=72, color=(0.04, 0.09, 0.16, 1.0)),
            label(
                name="hint",
                text="OSC Host = Mac IP · Send 8000 · Receive 9000",
                frame=(40, 460, 670, 80),
                size=16,
                color=(0.07, 0.14, 0.22, 1.0),
            ),
            button(name="taptic", frame=(40, 580, 670, 120), script=BUTTON_LUA),
            label(name="tapticLabel", text="Test Taptic", frame=(40, 710, 670, 40), size=18, color=(0.07, 0.14, 0.22, 1.0)),
        ]
    )
    root_props = common_props(
        name="Hear the Unseen",
        frame=(0, 0, 750, 1334),
        color=(0.027, 0.067, 0.114, 1.0),
        interactive=False,
        grab_focus=False,
        outline_style=0,
        script=LUA,
    )
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<lexml version='6'>"
        f"<node ID='{uid()}' type='GROUP'><includes></includes>"
        f"<properties>{root_props}</properties>"
        f"<values>{value_xml('touch', 'false')}</values>"
        f"<children>{children}</children>"
        "</node></lexml>"
    )


def main() -> None:
    xml = build_xml()
    out_dir = ROOT / "touchosc"
    out_dir.mkdir(exist_ok=True)
    xml_path = out_dir / "HearTheUnseen.xml"
    tosc_path = out_dir / "HearTheUnseen.tosc"
    xml_path.write_text(xml, encoding="utf-8")
    tosc_path.write_bytes(zlib.compress(xml.encode("utf-8")))
    print(f"Wrote {tosc_path} and {xml_path}")


if __name__ == "__main__":
    main()
