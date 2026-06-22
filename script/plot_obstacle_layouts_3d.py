"""Render the 20 simulation-suite obstacle layouts as interactive 3D scenes
in a single HTML file using plotly. Each scene contains the obstacle bodies
(spheres as triangulated surfaces, cubes as rotated boxes), the drone start,
the target, and the straight-line start->target.

Output: results/simulation_suite/obstacle_layouts_3d.html

This script rebuilds env 0 of each scenario via the existing
`build_layout` helper in script/plot_obstacle_layouts.py (CPU-only; no policy
inference). The rotation matrix matches pytorch3d's
`euler_angles_to_matrix(..., 'XYZ')` so cube poses agree with what the
collision/sensor code uses at runtime.
"""

import sys
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import torch
from omegaconf import OmegaConf
from plotly.subplots import make_subplots

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO_ROOT.parent))

from script.plot_obstacle_layouts import build_layout
from script.run_simulation_suite import BATCHES, find_latest_checkpoint


# --- mesh helpers --------------------------------------------------------

def _sphere_template(n_lat: int = 10, n_lon: int = 16):
    """Unit-radius sphere centred at origin: vertices + triangle faces."""
    phi = np.linspace(0, np.pi, n_lat)
    theta = np.linspace(0, 2 * np.pi, n_lon, endpoint=False)
    verts = np.array([
        [np.sin(p) * np.cos(t), np.sin(p) * np.sin(t), np.cos(p)]
        for p in phi for t in theta
    ])  # [n_lat*n_lon, 3]
    faces = []
    for pi in range(n_lat - 1):
        for ti in range(n_lon):
            tn = (ti + 1) % n_lon
            v00 = pi * n_lon + ti
            v01 = pi * n_lon + tn
            v10 = (pi + 1) * n_lon + ti
            v11 = (pi + 1) * n_lon + tn
            faces.append([v00, v10, v11])
            faces.append([v00, v11, v01])
    return verts, np.array(faces, dtype=np.int64)


def merged_sphere_mesh(centers, radii):
    """Single Mesh3d covering every sphere in a scene."""
    if len(centers) == 0:
        return None
    tv, tf = _sphere_template()
    n_per = len(tv)
    xs, ys, zs, ii, jj, kk = [], [], [], [], [], []
    offset = 0
    for c, r in zip(centers, radii):
        v = tv * r + np.asarray(c)
        f = tf + offset
        xs.extend(v[:, 0]); ys.extend(v[:, 1]); zs.extend(v[:, 2])
        ii.extend(f[:, 0]); jj.extend(f[:, 1]); kk.extend(f[:, 2])
        offset += n_per
    return xs, ys, zs, ii, jj, kk


def _rotation_xyz(rpy):
    """Rotation matrix matching pytorch3d.transforms.euler_angles_to_matrix('XYZ')."""
    rx, ry, rz = rpy
    cx, sx = np.cos(rx), np.sin(rx)
    cy, sy = np.cos(ry), np.sin(ry)
    cz, sz = np.cos(rz), np.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx,  cx]])
    Ry = np.array([[ cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rx @ Ry @ Rz


_BOX_FACES = np.array([
    [0, 1, 2], [0, 2, 3],          # bottom (-z)
    [4, 5, 6], [4, 6, 7],          # top    (+z)
    [0, 1, 5], [0, 5, 4],          # -y face
    [1, 2, 6], [1, 6, 5],          # +x face
    [2, 3, 7], [2, 7, 6],          # +y face
    [3, 0, 4], [3, 4, 7],          # -x face
], dtype=np.int64)


def merged_cube_mesh(centers, lwh, rpy):
    if len(centers) == 0:
        return None
    xs, ys, zs, ii, jj, kk = [], [], [], [], [], []
    offset = 0
    for c, (l, w, h), rot in zip(centers, lwh, rpy):
        # 8 corners in body frame
        corners = np.array([
            [-l/2, -w/2, -h/2],
            [ l/2, -w/2, -h/2],
            [ l/2,  w/2, -h/2],
            [-l/2,  w/2, -h/2],
            [-l/2, -w/2,  h/2],
            [ l/2, -w/2,  h/2],
            [ l/2,  w/2,  h/2],
            [-l/2,  w/2,  h/2],
        ])
        R = _rotation_xyz(rot)
        world = corners @ R.T + np.asarray(c)  # [8, 3]
        xs.extend(world[:, 0]); ys.extend(world[:, 1]); zs.extend(world[:, 2])
        f = _BOX_FACES + offset
        ii.extend(f[:, 0]); jj.extend(f[:, 1]); kk.extend(f[:, 2])
        offset += 8
    return xs, ys, zs, ii, jj, kk


# --- main ----------------------------------------------------------------

def add_scene(fig, row, col, sim, data):
    s = merged_sphere_mesh(data["p_spheres"], data["r_spheres"])
    c = merged_cube_mesh(data["p_cubes"], data["lwh_cubes"], data["rpy_cubes"])

    traces = []
    if s is not None:
        xs, ys, zs, ii, jj, kk = s
        traces.append(go.Mesh3d(
            x=xs, y=ys, z=zs, i=ii, j=jj, k=kk,
            color="#5c6bc0", opacity=0.55, flatshading=True,
            name="spheres", showlegend=False,
            hovertemplate="sphere<extra></extra>",
        ))
    if c is not None:
        xs, ys, zs, ii, jj, kk = c
        traces.append(go.Mesh3d(
            x=xs, y=ys, z=zs, i=ii, j=jj, k=kk,
            color="#8d6e63", opacity=0.65, flatshading=True,
            name="cubes", showlegend=False,
            hovertemplate="cube<extra></extra>",
        ))

    init = data["init"]; target = data["target"]
    traces.append(go.Scatter3d(
        x=[init[0], target[0]], y=[init[1], target[1]], z=[init[2], target[2]],
        mode="lines",
        line=dict(color="#1976d2", width=4, dash="dash"),
        showlegend=False, hoverinfo="skip",
    ))
    traces.append(go.Scatter3d(
        x=[init[0]], y=[init[1]], z=[init[2]],
        mode="markers",
        marker=dict(size=6, color="#43a047",
                    line=dict(color="black", width=1)),
        name="start", showlegend=False,
        hovertemplate="start<br>(%{x:.1f}, %{y:.1f}, %{z:.1f})<extra></extra>",
    ))
    traces.append(go.Scatter3d(
        x=[target[0]], y=[target[1]], z=[target[2]],
        mode="markers",
        marker=dict(size=8, color="#e53935", symbol="diamond",
                    line=dict(color="black", width=1)),
        name="target", showlegend=False,
        hovertemplate="target<br>(%{x:.1f}, %{y:.1f}, %{z:.1f})<extra></extra>",
    ))

    for tr in traces:
        fig.add_trace(tr, row=row, col=col)

    # axis ranges
    L = data["L"]
    height_scale = 0.25
    z_world_max = float(np.max([
        max([p[2] + r for p, r in zip(data["p_spheres"], data["r_spheres"])] or [0]),
        max([p[2] + h / 2 for p, (_, _, h) in zip(data["p_cubes"], data["lwh_cubes"])] or [0]),
        init[2], target[2], 1.0,
    ]))
    z_world_min = float(np.min([
        min([p[2] - r for p, r in zip(data["p_spheres"], data["r_spheres"])] or [0]),
        min([p[2] - h / 2 for p, (_, _, h) in zip(data["p_cubes"], data["lwh_cubes"])] or [0]),
        init[2], target[2], -1.0,
    ]))
    # match the env's z range too
    z_range = (min(z_world_min, -height_scale * L - 1),
               max(z_world_max,  height_scale * L + 1))

    scene_kwargs = dict(
        xaxis=dict(range=[-L, L], title="x", showbackground=False),
        yaxis=dict(range=[-L, L], title="y", showbackground=False),
        zaxis=dict(range=list(z_range), title="z", showbackground=False),
        aspectmode="manual",
        aspectratio=dict(x=1, y=1,
                         z=(z_range[1] - z_range[0]) / (2 * L)),
        camera=dict(eye=dict(x=1.6, y=1.6, z=0.9)),
    )
    fig.update_scenes(**scene_kwargs, row=row, col=col)


def main():
    cfg_path = REPO_ROOT / "outputs" / "train" / "2026-04-09" / "19-45-56" / ".hydra" / "config.yaml"
    if not cfg_path.exists():
        ckpt = find_latest_checkpoint()
        cfg_path = ckpt.parent / ".hydra" / "config.yaml"
    base_cfg = OmegaConf.load(cfg_path)
    device = torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu")
    print(f"[layouts3d] base cfg = {cfg_path}")
    print(f"[layouts3d] device   = {device}")

    sim_configs = BATCHES["all"]
    cols = 4
    rows = (len(sim_configs) + cols - 1) // cols
    titles = [
        (f"<b>{s['label']}</b><br>"
         f"L={int(s['length'])}, obs={s['n_obstacles']}, sph%={s['sphere_pct']}<br>"
         f"vel=[{s['min_vel']},{s['max_vel']}], randpos={s['randpos']}")
        for s in sim_configs
    ]
    specs = [[{"type": "scene"} for _ in range(cols)] for _ in range(rows)]
    fig = make_subplots(rows=rows, cols=cols, specs=specs,
                        subplot_titles=titles,
                        horizontal_spacing=0.02, vertical_spacing=0.04)

    for idx, sim in enumerate(sim_configs):
        r = idx // cols + 1
        c = idx % cols + 1
        print(f"  {sim['label']}")
        data = build_layout(base_cfg, sim, device)
        add_scene(fig, r, c, sim, data)

    fig.update_layout(
        title=dict(text="Obstacle layouts for each of the 20 evaluation scenarios "
                        "— interactive 3D (env 0, scenario seed)",
                   x=0.5, xanchor="center", font=dict(size=16)),
        height=320 * rows, width=1400,
        margin=dict(t=120, b=20, l=10, r=10),
        showlegend=False,
        font=dict(size=10),
    )
    # Bump subplot title font down so they don't overflow
    for ann in fig["layout"]["annotations"]:
        ann["font"] = dict(size=9)

    out_path = REPO_ROOT / "results" / "simulation_suite" / "obstacle_layouts_3d.html"
    fig.write_html(str(out_path), include_plotlyjs="cdn", full_html=True)
    print(f"\n[layouts3d] wrote {out_path}  ({out_path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
