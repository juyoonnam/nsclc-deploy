"""
AWS Pipeline Status components — badges, lineage, deployment health.
"""

from dash import html
import dash_mantine_components as dmc

from nsclc_ui.layout.theme import COLORS

# ---------------------------------------------------------------------------
# Mock AWS metadata (replace with real boto3 calls when deployed)
# ---------------------------------------------------------------------------
AWS_META = {
    "step_functions": {
        "status": "SUCCEEDED",
        "execution_id": "arn:aws:states:ap-northeast-2:...:nsclc-pipeline:2026-04-28",
        "last_run": "2026-04-28 22:08 KST",
        "duration": "6m 12s",
    },
    "sagemaker_training": {
        "job_name": "e2-tcga-crispr-20260428",
        "status": "Completed",
        "duration": "4.9 min",
        "instance": "ml.m5.xlarge",
        "cost_estimate": "$0.23",
    },
    "sagemaker_endpoint": {
        "name": "nsclc-rank-prod",
        "status": "Not Deployed",
        "p50_latency": "~120ms (estimate)",
        "p95_latency": "~350ms (estimate)",
    },
    "s3": {
        "bucket": "nsclc-engine-ap-northeast-2",
        "data_path": "s3://nsclc-engine/data/modality_scores_v1.csv",
        "last_modified": "2026-04-28 22:08",
    },
    "model_registry": {
        "model_name": "E6",
        "version": "v1.0.0",
        "status": "Approved",
    },
}


def pipeline_status_badge():
    """Step Functions execution status badge."""
    sf = AWS_META["step_functions"]
    color = "green" if sf["status"] == "SUCCEEDED" else "red"
    return dmc.Badge(
        f"Pipeline: {sf['status']}",
        color=color, variant="light", size="sm",
    )


def training_job_badge():
    """SageMaker Training Job badge."""
    tj = AWS_META["sagemaker_training"]
    return dmc.Group([
        dmc.Badge(f"Job: {tj['job_name']}", color="blue", variant="light", size="sm"),
        dmc.Badge(f"{tj['duration']}", color="gray", variant="light", size="sm"),
    ], gap=4)


def endpoint_status_badge():
    """SageMaker Endpoint status."""
    ep = AWS_META["sagemaker_endpoint"]
    color = "green" if ep["status"] == "InService" else "yellow" if ep["status"] == "Creating" else "gray"
    return dmc.Badge(
        f"Endpoint: {ep['status']}",
        color=color, variant="light", size="sm",
    )


def data_freshness_badge():
    """S3 data freshness."""
    s3 = AWS_META["s3"]
    return dmc.Text(
        f"Last scored: {s3['last_modified']} | Source: {s3['data_path']}",
        size="xs", c="dimmed", style={"fontSize": "10px"},
    )


def lineage_timeline():
    """AWS Provenance Timeline — horizontal pipeline DAG with status badges."""
    stages = [
        ("S3 Raw Data",        "active",       "s3://nsclc-engine/data/"),
        ("Glue/Athena QA",     "planned",      "Data quality checks"),
        ("Feature Store",      "planned",      "948 features"),
        ("SageMaker Training", "active",       "4.9min · ml.m5.xlarge"),
        ("Model Registry",     "active",       "E6 v1.0.0"),
        ("SageMaker Endpoint", "not_deployed", "nsclc-rank-prod"),
        ("Step Functions",     "active",       "Pipeline orchestration"),
        ("CloudWatch",         "active",       "Monitoring + alarms"),
    ]

    _STATUS_STYLE = {
        "active": {
            "bg": COLORS["success_bg"], "border_color": COLORS["success_text"],
            "text_color": COLORS["success_text"], "border_style": "solid",
            "badge": "✔ Active",
        },
        "planned": {
            "bg": COLORS["bg_tertiary"], "border_color": COLORS["text_tertiary"],
            "text_color": COLORS["text_tertiary"], "border_style": "dashed",
            "badge": "○ Planned",
        },
        "not_deployed": {
            "bg": COLORS["danger_bg"], "border_color": COLORS["danger_text"],
            "text_color": COLORS["danger_text"], "border_style": "dashed",
            "badge": "✖ Not deployed",
        },
    }

    nodes = []
    for i, (name, status, detail) in enumerate(stages):
        st = _STATUS_STYLE[status]
        nodes.append(
            html.Div([
                html.Div(style={
                    "width": "14px", "height": "14px", "borderRadius": "50%",
                    "background": st["bg"],
                    "border": f"2px {st['border_style']} {st['border_color']}",
                }),
                dmc.Text(name, size="xs", style={
                    "fontSize": "9px", "color": st["text_color"],
                    "fontWeight": "500", "textAlign": "center", "maxWidth": "80px",
                }),
                dmc.Text(detail, size="xs", style={
                    "fontSize": "8px", "color": COLORS["text_tertiary"],
                    "textAlign": "center", "maxWidth": "80px",
                }),
            ], style={
                "display": "flex", "flexDirection": "column",
                "alignItems": "center", "gap": "3px",
            })
        )
        if i < len(stages) - 1:
            nodes.append(html.Div(style={
                "flex": "1", "height": "2px", "minWidth": "16px",
                "background": COLORS["border"],
                "alignSelf": "center", "marginTop": "-20px",
            }))

    return html.Div(nodes, style={
        "display": "flex", "alignItems": "flex-start",
        "gap": "4px", "padding": "8px 0",
    })


def deployment_health_panel():
    """Deployment health summary for Model Card."""
    ep = AWS_META["sagemaker_endpoint"]
    return dmc.SimpleGrid(cols=4, spacing="xs", children=[
        dmc.Paper([
            dmc.Text("Endpoint", size="xs", c="dimmed"),
            dmc.Text(ep["status"], fw=600, size="sm",
                     style={"color": COLORS["success_text"] if ep["status"] == "InService" else COLORS["text_tertiary"]}),
        ], p="xs", radius="md", style={"background": COLORS["bg_secondary"]}),
        dmc.Paper([
            dmc.Text("p50 Latency", size="xs", c="dimmed"),
            dmc.Text(ep["p50_latency"], fw=600, size="sm"),
        ], p="xs", radius="md", style={"background": COLORS["bg_secondary"]}),
        dmc.Paper([
            dmc.Text("p95 Latency", size="xs", c="dimmed"),
            dmc.Text(ep["p95_latency"], fw=600, size="sm"),
        ], p="xs", radius="md", style={"background": COLORS["bg_secondary"]}),
        dmc.Paper([
            dmc.Text("Model Version", size="xs", c="dimmed"),
            dmc.Text(AWS_META["model_registry"]["version"], fw=600, size="sm"),
        ], p="xs", radius="md", style={"background": COLORS["bg_secondary"]}),
    ])


def inference_meta_panel():
    """Collapsible inference metadata for Candidate Explorer."""
    meta = AWS_META
    return dmc.Accordion(
        children=[
            dmc.AccordionItem(
                value="aws-meta",
                children=[
                    dmc.AccordionControl(
                        dmc.Text("AWS Inference Metadata", size="xs", fw=500),
                    ),
                    dmc.AccordionPanel(
                        dmc.Stack([
                            dmc.Group([
                                dmc.Text("Endpoint:", size="xs", c="dimmed", style={"width": "100px"}),
                                dmc.Text(meta["sagemaker_endpoint"]["name"], size="xs", ff="monospace"),
                                endpoint_status_badge(),
                            ], gap=8),
                            dmc.Group([
                                dmc.Text("Model:", size="xs", c="dimmed", style={"width": "100px"}),
                                dmc.Text(f"{meta['model_registry']['model_name']} {meta['model_registry']['version']}", size="xs", ff="monospace"),
                            ], gap=8),
                            dmc.Group([
                                dmc.Text("Training Job:", size="xs", c="dimmed", style={"width": "100px"}),
                                dmc.Text(meta["sagemaker_training"]["job_name"], size="xs", ff="monospace"),
                            ], gap=8),
                            dmc.Group([
                                dmc.Text("Last Retrain:", size="xs", c="dimmed", style={"width": "100px"}),
                                dmc.Text("2026-04-28", size="xs"),
                            ], gap=8),
                            dmc.Text("⚠ Mock metadata — replace with boto3 calls in production",
                                     size="xs", c="dimmed", fs="italic", mt=4),
                        ], gap=4),
                    ),
                ],
            ),
        ],
        variant="separated",
        radius="md",
    )
