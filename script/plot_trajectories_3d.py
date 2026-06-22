"""Render v3 vs v4 drone trajectories in 3D for the three captured scenarios.

Reads:
  results/simulation_suite/trajectories_v3.pkl
  results/simulation_suite/trajectories_v4.pkl

Writes:
  results/simulation_suite/trajectories_3d.html

Layout: 3 rows (one per scenario) x 2 columns (v3 left, v4 right). Each cell
is a 3D plotly scene with the scenario's obstacles, drone start (green dot),
target (red diamond), and the policy's xyz trajectory rendered as a colored
line (timestep -> color along a viridis ramp). The line is annotated with
the outcome (success / collision / timeout) and the elapsed sim time.
"""

import pickle
import sys
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO_ROOT.parent))

from script.plot_obstacle_layouts_3d import (
    merged_sphere_mesh, merged_cube_mesh,
)

ROOT = REPO_ROOT / "results" / "simulation_suite"
V3_PKL = ROOT / "trajectories_v3.pkl"
V4_PKL = ROOT / "trajectories_v4.pkl"
OUT = ROOT / "trajectories_3d.html"

OUTCOME_COLOR = {
    "success":   "#2e7d32",
    "collision": "#c62828",
    "timeout":   "#ef6c00",
    "ongoing":   "#1976d2",
}


def add_scene(fig, row, col, label, version, data):
    obs = data["obstacles"]
    pos = data["positions"]
    dt = data["dt"]
    n_steps = pos.shape[0]
    t = np.arange(n_steps) * dt

    # obstacles
    s = merged_sphere_mesh(obs["p_spheres"], obs["r_spheres"])
    c = merged_cube_mesh(obs["p_cubes"], obs["lwh_cubes"], obs["rpy_cubes"])
    if s is not None:
        xs, ys, zs, ii, jj, kk = s
        fig.add_trace(go.Mesh3d(
            x=xs, y=ys, z=zs, i=ii, j=jj, k=kk,
            color="#5c6bc0", opacity=0.35, flatshading=True,
            showlegend=False, hoverinfo="skip",
        ), row=row, col=col)
    if c is not None:
        xs, ys, zs, ii, jj, kk = c
        fig.add_trace(go.Mesh3d(
            x=xs, y=ys, z=zs, i=ii, j=jj, k=kk,
            color="#8d6e63", opacity=0.45, flatshading=True,
            showlegend=False, hoverinfo="skip",
        ), row=row, col=col)

    init = obs["init"]; target = obs["target"]
    fig.add_trace(go.Scatter3d(
        x=[init[0], target[0]], y=[init[1], target[1]], z=[init[2], target[2]],
        mode="lines",
        line=dict(color="#1976d2", width=2, dash="dash"),
        showlegend=False, hoverinfo="skip",
    ), row=row, col=col)
    fig.add_trace(go.Scatter3d(
        x=[init[0]], y=[init[1]], z=[init[2]],
        mode="markers",
        marker=dict(size=6, color="#43a047", line=dict(color="black", width=1)),
        showlegend=False, hovertemplate="start<extra></extra>",
    ), row=row, col=col)
    fig.add_trace(go.Scatter3d(
        x=[target[0]], y=[target[1]], z=[target[2]],
        mode="markers",
        marker=dict(size=8, color="#e53935", symbol="diamond",
                    line=dict(color="black", width=1)),
        showlegend=False, hovertemplate="target<extra></extra>",
    ), row=row, col=col)

    # trajectory (color encodes time)
    fig.add_trace(go.Scatter3d(
        x=pos[:, 0], y=pos[:, 1], z=pos[:, 2],
        mode="lines+markers",
        line=dict(color=t, colorscale="Viridis", width=6),
        marker=dict(size=2, color=t, colorscale="Viridis",
                    showscale=False),
        showlegend=False,
        hovertemplate=("t=%{customdata:.2f}s<br>"
                       "x=%{x:.2f}, y=%{y:.2f}, z=%{z:.2f}<extra></extra>"),
        customdata=t,
    ), row=row, col=col)

    # endpoint marker colored by outcome
    end_color = OUTCOME_COLOR.get(data["outcome"], "#444")
    fig.add_trace(go.Scatter3d(
        x=[pos[-1, 0]], y=[pos[-1, 1]], z=[pos[-1, 2]],
        mode="markers",
        marker=dict(size=10, color=end_color, symbol="x",
                    line=dict(color="black", width=1)),
        showlegend=False,
        hovertemplate=f"end ({data['outcome']})<extra></extra>",
    ), row=row, col=col)

    # scene formatting
    L = obs["L"]
    height_scale = 0.25
    z_world_max = float(max([p[2] + r for p, r in zip(obs["p_spheres"], obs["r_spheres"])] + [pos[:, 2].max(), 1.0]))
    z_world_min = float(min([p[2] - r for p, r in zip(obs["p_spheres"], obs["r_spheres"])] + [pos[:, 2].min(), -1.0]))
    z_range = (min(z_world_min, -height_scale * L - 1),
               max(z_world_max,  height_scale * L + 1))
    fig.update_scenes(
        xaxis=dict(range=[-L, L], title="x", showbackground=False),
        yaxis=dict(range=[-L, L], title="y", showbackground=False),
        zaxis=dict(range=list(z_range), title="z", showbackground=False),
        aspectmode="manual",
        aspectratio=dict(x=1, y=1, z=(z_range[1] - z_range[0]) / (2 * L)),
        camera=dict(eye=dict(x=1.5, y=1.5, z=0.9)),
        row=row, col=col,
    )


def main():
    with V3_PKL.open("rb") as f:
        v3 = pickle.load(f)
    with V4_PKL.open("rb") as f:
        v4 = pickle.load(f)

    labels = list(v3.keys())  # same order in both pickles
    n = len(labels)

    titles = []
    for label in labels:
        for ver, data in (("v3", v3), ("v4", v4)):
            d = data[label]
            t_end = d["positions"].shape[0] * d["dt"]
            titles.append(f"<b>{label}</b> &mdash; {ver} &mdash; "
                          f"{d['outcome']} at t={t_end:.1f}s")

    specs = [[{"type": "scene"}, {"type": "scene"}] for _ in range(n)]
    fig = make_subplots(rows=n, cols=2, specs=specs,
                        subplot_titles=titles,
                        horizontal_spacing=0.02, vertical_spacing=0.06)

    for row, label in enumerate(labels, start=1):
        add_scene(fig, row, 1, label, "v3", v3[label])
        add_scene(fig, row, 2, label, "v4", v4[label])

    fig.update_layout(
        title=dict(
            text=("Drone xyz trajectory: v3 vs v4 — env 0, first episode<br>"
                  "<span style='font-size:11px'>"
                  "Trajectory color = elapsed time (purple→yellow). "
                  "X marker = end of episode (green=success, orange=timeout, red=collision)."
                  "</span>"),
            x=0.5, xanchor="center", font=dict(size=15)),
        height=520 * n, width=1500,
        margin=dict(t=120, b=20, l=10, r=10),
        showlegend=False, font=dict(size=10),
    )
    for ann in fig["layout"]["annotations"]:
        ann["font"] = dict(size=11)

    fig.write_html(str(OUT), include_plotlyjs="cdn", full_html=True)
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
