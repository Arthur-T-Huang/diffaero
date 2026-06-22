"""Render true-3D side-by-side v3 vs v4 trajectory videos using plotly +
kaleido for per-frame PNG export, stitched into MP4 via imageio/ffmpeg.

Reads:
  results/simulation_suite/trajectories_v3.pkl
  results/simulation_suite/trajectories_v4.pkl

Writes (one per scenario):
  results/simulation_suite/trajectory_3d_{sim_label}.mp4

Frames are sampled at stride 2 and emitted at 15 fps so playback matches
real-time (1 s of video = 1 s of simulated flight, same as the 2D videos).
"""

import io
import pickle
import sys
import time
from pathlib import Path
from typing import Dict

import imageio.v2 as imageio
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO_ROOT))

from script.plot_obstacle_layouts_3d import merged_sphere_mesh, merged_cube_mesh

ROOT = REPO_ROOT / "results" / "simulation_suite"
STRIDE = 2          # render every other sim step
TARGET_FPS = 15     # 15 fps × 2 steps per frame × 0.0333 s/step ≈ 1.0 s/s
WIDTH = 1100
HEIGHT = 520

OUTCOME_COLOR = {
    "success":   "#2e7d32",
    "collision": "#c62828",
    "timeout":   "#ef6c00",
    "ongoing":   "#1976d2",
}


def add_static(fig, col, data):
    """Add the obstacle field + start + target + straight-line goal to the scene."""
    obs = data["obstacles"]
    s = merged_sphere_mesh(obs["p_spheres"], obs["r_spheres"])
    c = merged_cube_mesh(obs["p_cubes"], obs["lwh_cubes"], obs["rpy_cubes"])
    if s is not None:
        xs, ys, zs, ii, jj, kk = s
        fig.add_trace(go.Mesh3d(x=xs, y=ys, z=zs, i=ii, j=jj, k=kk,
                                color="#5c6bc0", opacity=0.35,
                                flatshading=True, hoverinfo="skip"),
                      row=1, col=col)
    if c is not None:
        xs, ys, zs, ii, jj, kk = c
        fig.add_trace(go.Mesh3d(x=xs, y=ys, z=zs, i=ii, j=jj, k=kk,
                                color="#8d6e63", opacity=0.45,
                                flatshading=True, hoverinfo="skip"),
                      row=1, col=col)
    init = obs["init"]; target = obs["target"]
    fig.add_trace(go.Scatter3d(
        x=[init[0], target[0]], y=[init[1], target[1]], z=[init[2], target[2]],
        mode="lines",
        line=dict(color="#1976d2", width=2, dash="dash"),
        hoverinfo="skip",
    ), row=1, col=col)
    fig.add_trace(go.Scatter3d(
        x=[init[0]], y=[init[1]], z=[init[2]],
        mode="markers",
        marker=dict(size=6, color="#43a047", line=dict(color="black", width=1)),
        hoverinfo="skip",
    ), row=1, col=col)
    fig.add_trace(go.Scatter3d(
        x=[target[0]], y=[target[1]], z=[target[2]],
        mode="markers",
        marker=dict(size=8, color="#e53935", symbol="diamond",
                    line=dict(color="black", width=1)),
        hoverinfo="skip",
    ), row=1, col=col)


def build_frame(label: str, v3: Dict, v4: Dict, frame_idx: int) -> bytes:
    """Return one frame as a PNG byte-string."""
    n3 = v3["positions"].shape[0]
    n4 = v4["positions"].shape[0]
    dt = v3["dt"]

    titles = []
    for ver, data, n in (("v3", v3, n3), ("v4", v4, n4)):
        t = min(frame_idx, n - 1) * dt
        active = frame_idx < n
        suffix = "" if active else f"- {data['outcome'].upper()}"
        titles.append(f"{ver}  t={t:5.2f}s {suffix}")

    fig = make_subplots(
        rows=1, cols=2,
        specs=[[{"type": "scene"}, {"type": "scene"}]],
        subplot_titles=titles,
        horizontal_spacing=0.02,
    )

    for col, (ver, data, n) in enumerate(
            (("v3", v3, n3), ("v4", v4, n4)), start=1):
        add_static(fig, col, data)
        step = min(frame_idx, n - 1)
        pos = data["positions"][:step + 1]
        active = frame_idx < n

        # trajectory so far
        fig.add_trace(go.Scatter3d(
            x=pos[:, 0], y=pos[:, 1], z=pos[:, 2],
            mode="lines",
            line=dict(color="#0d47a1", width=5),
            hoverinfo="skip",
        ), row=1, col=col)

        # current head (or final colored marker if episode ended)
        head_color = "#0d47a1" if active else OUTCOME_COLOR.get(data["outcome"], "#444")
        head_symbol = "circle" if active else "x"
        head_size = 7 if active else 10
        fig.add_trace(go.Scatter3d(
            x=[pos[-1, 0]], y=[pos[-1, 1]], z=[pos[-1, 2]],
            mode="markers",
            marker=dict(size=head_size, color=head_color, symbol=head_symbol,
                        line=dict(color="black", width=1)),
            hoverinfo="skip",
        ), row=1, col=col)

        obs = data["obstacles"]
        L = obs["L"]
        height_scale = 0.25
        z_range = (-height_scale * L - 1, height_scale * L + 1)
        fig.update_scenes(
            xaxis=dict(range=[-L, L], showbackground=False,
                       showgrid=True, gridcolor="#ddd"),
            yaxis=dict(range=[-L, L], showbackground=False,
                       showgrid=True, gridcolor="#ddd"),
            zaxis=dict(range=list(z_range), showbackground=False,
                       showgrid=True, gridcolor="#ddd"),
            aspectmode="manual",
            aspectratio=dict(x=1, y=1,
                             z=(z_range[1] - z_range[0]) / (2 * L)),
            camera=dict(eye=dict(x=1.6, y=1.6, z=0.9)),
            row=1, col=col,
        )

    fig.update_layout(
        title=dict(text=f"{label}", x=0.5, xanchor="center", font=dict(size=14)),
        width=WIDTH, height=HEIGHT,
        showlegend=False,
        margin=dict(t=60, b=10, l=10, r=10),
        font=dict(size=10),
    )
    for ann in fig["layout"]["annotations"]:
        ann["font"] = dict(size=11)

    return fig.to_image(format="png", width=WIDTH, height=HEIGHT, engine="kaleido")


def render_one(label: str, v3: Dict, v4: Dict):
    n = max(v3["positions"].shape[0], v4["positions"].shape[0])
    out_path = ROOT / f"trajectory_3d_{label}.mp4"
    print(f"  rendering {label}: {n} sim steps, stride {STRIDE}, "
          f"~{n // STRIDE} frames @ {TARGET_FPS} fps -> {out_path.name}")

    n_frames = (n + STRIDE - 1) // STRIDE
    t_started = time.time()
    last_print = t_started
    with imageio.get_writer(str(out_path), fps=TARGET_FPS, codec="libx264",
                            quality=8, macro_block_size=1) as writer:
        for i, frame_idx in enumerate(range(0, n, STRIDE)):
            png = build_frame(label, v3, v4, frame_idx)
            img = imageio.imread(io.BytesIO(png))
            writer.append_data(img)
            if time.time() - last_print > 20.0:
                rate = (i + 1) / (time.time() - t_started)
                eta = (n_frames - i - 1) / max(rate, 1e-6)
                print(f"    frame {i+1}/{n_frames}  "
                      f"({rate:.2f} fr/s, ETA {eta:.0f}s)")
                last_print = time.time()

    print(f"  wrote {out_path} "
          f"({out_path.stat().st_size / (1024 * 1024):.2f} MB) "
          f"in {time.time() - t_started:.0f}s")


def main():
    with (ROOT / "trajectories_v3.pkl").open("rb") as f:
        v3 = pickle.load(f)
    with (ROOT / "trajectories_v4.pkl").open("rb") as f:
        v4 = pickle.load(f)
    for label in v3.keys():
        render_one(label, v3[label], v4[label])


if __name__ == "__main__":
    main()
