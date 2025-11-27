#!/usr/bin/env python3
"""
Trace UN document genealogy backwards from final resolutions.

This script provides tools to navigate the document tree from a resolution
back through committee reports, drafts, meeting records, and agenda items.
"""

import argparse
import html
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from collections import defaultdict


# Default data locations
DEFAULT_DATA_ROOT = Path(__file__).parent / "data"
DEFAULT_PARSED_HTML = DEFAULT_DATA_ROOT / "parsed" / "html"
DEFAULT_PARSED_PDFS = DEFAULT_DATA_ROOT / "parsed" / "pdfs"


@dataclass
class DocumentReference:
    """A reference to a related UN document."""
    symbol: str
    url: Optional[str] = None
    doc_type: Optional[str] = None  # resolution, draft, committee_report, meeting, agenda


class UNDocumentIndex:
    """Index of all UN documents for fast lookup by symbol."""

    def __init__(self, data_root: Path = DEFAULT_PARSED_HTML):
        self.data_root = Path(data_root)
        self.documents: Dict[str, Path] = {}
        self._build_index()

    def _build_index(self):
        """Build index of all documents by symbol."""
        # Index HTML parsed documents
        for doc_type_dir in self.data_root.iterdir():
            if not doc_type_dir.is_dir():
                continue

            for json_file in doc_type_dir.glob("*.json"):
                try:
                    with open(json_file) as f:
                        data = json.load(f)
                        symbol = data.get("metadata", {}).get("symbol")
                        if symbol:
                            # Normalize symbol (remove spaces, etc.)
                            normalized = self._normalize_symbol(symbol)
                            self.documents[normalized] = json_file
                except Exception as e:
                    print(f"Warning: Failed to index {json_file}: {e}")

        # Also index PDF parsed documents
        pdf_root = DEFAULT_PARSED_PDFS
        if pdf_root.exists():
            for doc_type_dir in pdf_root.iterdir():
                if not doc_type_dir.is_dir():
                    continue

                for json_file in doc_type_dir.glob("*.json"):
                    try:
                        with open(json_file) as f:
                            data = json.load(f)
                            # For PDF parsed docs, extract symbol from filename
                            # e.g., A_C.3_78_L.41.json -> A/C.3/78/L.41
                            symbol = json_file.stem.replace("_", "/").replace(".json", "")
                            normalized = self._normalize_symbol(symbol)
                            if normalized not in self.documents:
                                self.documents[normalized] = json_file
                    except Exception as e:
                        print(f"Warning: Failed to index {json_file}: {e}")

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """Normalize document symbol for lookup."""
        # Remove spaces, convert to uppercase
        normalized = symbol.strip().upper()
        # Normalize separators
        normalized = normalized.replace("_", "/")
        return normalized

    def find(self, symbol: str) -> Optional[Path]:
        """Find document by symbol."""
        normalized = self._normalize_symbol(symbol)
        return self.documents.get(normalized)

    def load(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Load document data by symbol."""
        path = self.find(symbol)
        if path:
            with open(path) as f:
                return json.load(f)
        return None


class DocumentGenealogy:
    """Trace document genealogy backwards from resolution."""

    def __init__(self, index: UNDocumentIndex):
        self.index = index

    def trace_backwards(self, resolution_symbol: str) -> Dict[str, Any]:
        """Trace genealogy backwards from resolution to origins."""
        resolution = self.index.load(resolution_symbol)
        if not resolution:
            return {"error": f"Resolution {resolution_symbol} not found"}

        tree = {
            "mode": "backwards",
            "root_symbol": resolution_symbol,
            "resolution": {"symbol": resolution_symbol, "data": resolution},
            "drafts": [],
            "committee_reports": [],
            "meeting_records": [],
            "agenda_items": []
        }

        related = resolution.get("related_documents", {})

        for draft_ref in related.get("drafts", []):
            draft_symbol = draft_ref.get("text")
            tree["drafts"].append({
                "symbol": draft_symbol,
                "data": self.index.load(draft_symbol),
                "found": self.index.find(draft_symbol) is not None
            })

        for report_ref in related.get("committee_reports", []):
            report_symbol = report_ref.get("text")
            tree["committee_reports"].append({
                "symbol": report_symbol,
                "data": self.index.load(report_symbol),
                "found": self.index.find(report_symbol) is not None
            })

        for meeting_ref in related.get("meeting_records", []):
            meeting_symbol = meeting_ref.get("text")
            tree["meeting_records"].append({
                "symbol": meeting_symbol,
                "data": self.index.load(meeting_symbol),
                "found": self.index.find(meeting_symbol) is not None
            })

        for agenda_item in resolution.get("agenda", []):
            agenda_symbol = agenda_item.get("agenda_symbol")
            tree["agenda_items"].append({
                "symbol": agenda_symbol,
                "item_number": agenda_item.get("item_number"),
                "sub_item": agenda_item.get("sub_item"),
                "title": agenda_item.get("title"),
                "data": self.index.load(agenda_symbol),
                "found": self.index.find(agenda_symbol) is not None
            })

        return tree

    def trace_forwards(self, agenda_symbol: str, item_number: str = None) -> Dict[str, Any]:
        """Trace forwards from agenda item to all resulting documents."""
        agenda = self.index.load(agenda_symbol)
        if not agenda:
            return {"error": f"Agenda {agenda_symbol} not found"}

        tree = {
            "mode": "forwards",
            "root_symbol": agenda_symbol,
            "agenda": {"symbol": agenda_symbol, "data": agenda},
            "drafts": [],
            "committee_reports": [],
            "resolutions": [],
            "meetings": []
        }

        # Search all documents for ones that reference this agenda item
        for doc_symbol, doc_path in self.index.documents.items():
            doc_data = self.index.load(doc_symbol)
            if not doc_data:
                continue

            # Check if this doc references our agenda item
            for agenda_ref in doc_data.get("agenda", []):
                if agenda_ref.get("agenda_symbol") == agenda_symbol:
                    # Match item number if specified
                    if item_number:
                        ref_item = str(agenda_ref.get("item_number", ""))
                        if agenda_ref.get("sub_item"):
                            ref_item += agenda_ref.get("sub_item")
                        if ref_item != item_number:
                            continue

                    # Categorize by document type (from path)
                    doc_entry = {"symbol": doc_symbol, "data": doc_data, "found": True}

                    if "/resolutions/" in str(doc_path):
                        tree["resolutions"].append(doc_entry)
                    elif "/drafts/" in str(doc_path):
                        tree["drafts"].append(doc_entry)
                    elif "/committee-reports/" in str(doc_path):
                        tree["committee_reports"].append(doc_entry)
                    elif "/meetings/" in str(doc_path):
                        tree["meetings"].append(doc_entry)
                    break

        return tree

    def trace_from_draft(self, draft_symbol: str) -> Dict[str, Any]:
        """Trace both directions from a draft resolution."""
        draft = self.index.load(draft_symbol)
        if not draft:
            return {"error": f"Draft {draft_symbol} not found"}

        tree = {
            "mode": "draft",
            "root_symbol": draft_symbol,
            "draft": {"symbol": draft_symbol, "data": draft},
            "resolutions": [],
            "committee_reports": [],
            "agenda_items": []
        }

        # Get agenda items (backwards)
        for agenda_item in draft.get("agenda", []):
            agenda_symbol = agenda_item.get("agenda_symbol")
            tree["agenda_items"].append({
                "symbol": agenda_symbol,
                "item_number": agenda_item.get("item_number"),
                "sub_item": agenda_item.get("sub_item"),
                "data": self.index.load(agenda_symbol),
                "found": self.index.find(agenda_symbol) is not None
            })

        # Find documents that reference this draft (forwards)
        for doc_symbol, doc_path in self.index.documents.items():
            doc_data = self.index.load(doc_symbol)
            if not doc_data:
                continue

            # Check if this doc references our draft
            for draft_ref in doc_data.get("related_documents", {}).get("drafts", []):
                if draft_ref.get("text") == draft_symbol:
                    doc_entry = {"symbol": doc_symbol, "data": doc_data, "found": True}

                    if "/resolutions/" in str(doc_path):
                        tree["resolutions"].append(doc_entry)
                    elif "/committee-reports/" in str(doc_path):
                        tree["committee_reports"].append(doc_entry)
                    break

        return tree

    def print_tree(self, tree: Dict[str, Any], verbose: bool = False):
        """Print the document tree in a readable format."""
        if "error" in tree:
            print(f"❌ {tree['error']}")
            return

        # Detect mode and print accordingly
        if "resolution" in tree:
            self._print_backwards(tree, verbose)
        elif "agenda" in tree:
            self._print_forwards(tree, verbose)
        elif "draft" in tree:
            self._print_from_draft(tree, verbose)

    def _print_backwards(self, tree: Dict[str, Any], verbose: bool):
        """Print backwards trace from resolution."""
        res = tree["resolution"]
        data = res["data"]
        print(f"\n📄 RESOLUTION: {res['symbol']}")
        print(f"   Title: {data['metadata']['title']}")
        if data.get("voting"):
            print(f"   Voting: {data['voting'].get('raw_text', 'N/A')}")

        print(f"\n📋 AGENDA ITEMS ({len(tree['agenda_items'])})")
        for item in tree["agenda_items"]:
            status = "✓" if item["found"] else "✗"
            print(f"   {status} {item['symbol']} (Item {item.get('item_number', '?')}{item.get('sub_item', '')})")

        print(f"\n📝 DRAFTS ({len(tree['drafts'])})")
        for draft in tree["drafts"]:
            status = "✓" if draft["found"] else "✗"
            print(f"   {status} {draft['symbol']}")

        print(f"\n📊 COMMITTEE REPORTS ({len(tree['committee_reports'])})")
        for report in tree["committee_reports"]:
            status = "✓" if report["found"] else "✗"
            print(f"   {status} {report['symbol']}")

        print(f"\n🏛️  MEETINGS ({len(tree['meeting_records'])})")
        for meeting in tree["meeting_records"]:
            status = "✓" if meeting["found"] else "✗"
            print(f"   {status} {meeting['symbol']}")

    def _print_forwards(self, tree: Dict[str, Any], verbose: bool):
        """Print forwards trace from agenda."""
        agenda = tree["agenda"]
        data = agenda["data"]
        print(f"\n📋 AGENDA: {agenda['symbol']}")
        print(f"   Title: {data['metadata']['title']}")

        print(f"\n📝 DRAFTS ({len(tree['drafts'])})")
        for draft in tree["drafts"]:
            print(f"   ✓ {draft['symbol']}")

        print(f"\n📊 COMMITTEE REPORTS ({len(tree['committee_reports'])})")
        for report in tree["committee_reports"]:
            print(f"   ✓ {report['symbol']}")

        print(f"\n📄 RESOLUTIONS ({len(tree['resolutions'])})")
        for res in tree["resolutions"]:
            print(f"   ✓ {res['symbol']}")

        print(f"\n🏛️  MEETINGS ({len(tree['meetings'])})")
        for meeting in tree["meetings"]:
            print(f"   ✓ {meeting['symbol']}")

    def _print_from_draft(self, tree: Dict[str, Any], verbose: bool):
        """Print trace from draft in both directions."""
        draft = tree["draft"]
        data = draft["data"]
        print(f"\n📝 DRAFT: {draft['symbol']}")
        print(f"   Title: {data['metadata'].get('title', 'N/A')}")
        print(f"   Date: {data['metadata'].get('date', 'N/A')}")

        print(f"\n⬅️  BACKWARDS:")
        print(f"   📋 Agenda items: {len(tree['agenda_items'])}")
        for item in tree["agenda_items"]:
            status = "✓" if item["found"] else "✗"
            print(f"      {status} {item['symbol']} (Item {item.get('item_number', '?')}{item.get('sub_item', '')})")

        print(f"\n➡️  FORWARDS:")
        print(f"   📊 Committee reports: {len(tree['committee_reports'])}")
        for report in tree["committee_reports"]:
            print(f"      ✓ {report['symbol']}")

        print(f"   📄 Resolutions: {len(tree['resolutions'])}")
        for res in tree["resolutions"]:
            print(f"      ✓ {res['symbol']}")


GRAPH_DOC_TYPE_ORDER = [
    "agenda",
    "draft",
    "committee_report",
    "resolution",
    "meeting"
]

GRAPH_DOC_TYPE_LABELS = {
    "agenda": "Agenda",
    "draft": "Draft",
    "committee_report": "Committee report",
    "resolution": "Resolution",
    "meeting": "Meeting"
}


def _truncate(text: Optional[str], limit: int = 80) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _entry_title(entry: Dict[str, Any]) -> str:
    data = (entry or {}).get("data") or {}
    metadata = data.get("metadata") or {}
    return metadata.get("title") or metadata.get("symbol") or entry.get("symbol") or ""


def _agenda_unique_key(symbol: Optional[str], item_number: Any, sub_item: Any) -> str:
    symbol = symbol or "unknown-agenda"
    return f"{symbol}|{item_number}|{sub_item}"


def build_graph_from_tree(tree: Dict[str, Any]) -> Dict[str, Any]:
    if "error" in tree:
        raise ValueError(tree["error"])

    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, str]] = []

    def ensure_node(symbol: Optional[str], doc_type: str, *, title: Optional[str] = None,
                    found: Optional[bool] = None, extra: Optional[Dict[str, Any]] = None,
                    unique_key: Optional[str] = None) -> Optional[str]:
        if not symbol and doc_type != "agenda":
            return None

        node_id_source = unique_key or symbol or doc_type
        node_id = UNDocumentIndex._normalize_symbol(node_id_source)
        if node_id not in nodes:
            label = symbol or GRAPH_DOC_TYPE_LABELS.get(doc_type, doc_type.title())
            nodes[node_id] = {
                "id": node_id,
                "symbol": symbol or label,
                "doc_type": doc_type,
                "label": label,
                "title": _truncate(title or label),
                "found": True if found is None else bool(found),
                "extra": extra or {}
            }
        else:
            node = nodes[node_id]
            if title and not node.get("title"):
                node["title"] = _truncate(title)
            if extra:
                node["extra"].update(extra)
            if found is not None:
                node["found"] = node["found"] and bool(found)
        return node_id

    def add_edge(source: Optional[str], target: Optional[str], relation: str):
        if not source or not target:
            return
        edges.append({
            "source": source,
            "target": target,
            "relation": relation
        })

    mode = tree.get("mode")

    if "resolution" in tree:
        res = tree["resolution"]
        res_id = ensure_node(
            res.get("symbol"),
            "resolution",
            title=_entry_title(res)
        )

        for item in tree.get("agenda_items", []):
            unique_key = _agenda_unique_key(item.get("symbol"), item.get("item_number"), item.get("sub_item"))
            agenda_id = ensure_node(
                item.get("symbol"),
                "agenda",
                title=item.get("title"),
                found=item.get("found"),
                extra={
                    "item_number": item.get("item_number"),
                    "sub_item": item.get("sub_item")
                },
                unique_key=unique_key
            )
            add_edge(agenda_id, res_id, "resolution")

        for draft in tree.get("drafts", []):
            draft_id = ensure_node(
                draft.get("symbol"),
                "draft",
                title=_entry_title(draft),
                found=draft.get("found")
            )
            add_edge(draft_id, res_id, "resolution")

        for report in tree.get("committee_reports", []):
            report_id = ensure_node(
                report.get("symbol"),
                "committee_report",
                title=_entry_title(report),
                found=report.get("found")
            )
            add_edge(report_id, res_id, "resolution")

        for meeting in tree.get("meeting_records", []):
            meeting_id = ensure_node(
                meeting.get("symbol"),
                "meeting",
                title=_entry_title(meeting),
                found=meeting.get("found")
            )
            add_edge(meeting_id, res_id, "resolution")

    if "agenda" in tree:
        agenda = tree["agenda"]
        agenda_id = ensure_node(
            agenda.get("symbol"),
            "agenda",
            title=_entry_title(agenda)
        )

        for list_name in ("drafts", "committee_reports", "resolutions", "meetings"):
            for entry in tree.get(list_name, []):
                doc_type = {
                    "drafts": "draft",
                    "committee_reports": "committee_report",
                    "resolutions": "resolution",
                    "meetings": "meeting"
                }[list_name]
                node_id = ensure_node(
                    entry.get("symbol"),
                    doc_type,
                    title=_entry_title(entry),
                    found=entry.get("found", True)
                )
                add_edge(agenda_id, node_id, doc_type)

    if "draft" in tree:
        draft = tree["draft"]
        draft_id = ensure_node(
            draft.get("symbol"),
            "draft",
            title=_entry_title(draft)
        )

        for item in tree.get("agenda_items", []):
            unique_key = _agenda_unique_key(item.get("symbol"), item.get("item_number"), item.get("sub_item"))
            agenda_id = ensure_node(
                item.get("symbol"),
                "agenda",
                title=item.get("title"),
                found=item.get("found"),
                extra={
                    "item_number": item.get("item_number"),
                    "sub_item": item.get("sub_item")
                },
                unique_key=unique_key
            )
            add_edge(agenda_id, draft_id, "draft")

        for list_name in ("committee_reports", "resolutions"):
            for entry in tree.get(list_name, []):
                doc_type = "committee_report" if list_name == "committee_reports" else "resolution"
                node_id = ensure_node(
                    entry.get("symbol"),
                    doc_type,
                    title=_entry_title(entry),
                    found=entry.get("found", True)
                )
                add_edge(draft_id, node_id, doc_type)

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "meta": {
            "mode": mode,
            "root_symbol": tree.get("root_symbol")
        }
    }


def _sanitize_identifier(value: str, prefix: str, index: int) -> str:
    if not value:
        return f"{prefix}{index}"
    cleaned = re.sub(r"[^0-9A-Za-z_]+", "_", value)
    if not cleaned:
        cleaned = f"{prefix}{index}"
    elif cleaned[0].isdigit():
        cleaned = f"{prefix}{cleaned}"
    return cleaned


def graph_to_mermaid(graph: Dict[str, Any]) -> str:
    id_map: Dict[str, str] = {}
    lines = ["graph LR"]

    for idx, node in enumerate(graph.get("nodes", [])):
        safe_id = _sanitize_identifier(node.get("id"), "N", idx)
        id_map[node["id"]] = safe_id
        label = node.get("label", node.get("symbol", safe_id))
        title = node.get("title")
        lines.append(f"    {safe_id}(\"{label}\")")
        if title:
            lines.append(f"    click {safe_id} href \"#\" \"{title}\"")

    for edge in graph.get("edges", []):
        src = id_map.get(edge.get("source"))
        tgt = id_map.get(edge.get("target"))
        if not src or not tgt:
            continue
        relation = edge.get("relation", "")
        label = f"|{relation}|" if relation else ""
        lines.append(f"    {src} -->{label} {tgt}")

    return "\n".join(lines)


def graph_to_html(graph: Dict[str, Any], *, title: str) -> str:
    graph_json = json.dumps(graph).replace("</", "<\\/")
    legend_items = []
    for doc_type in GRAPH_DOC_TYPE_ORDER:
        legend_items.append(
            f"<span class=\"legend-pill type-{doc_type}\">{GRAPH_DOC_TYPE_LABELS.get(doc_type, doc_type.title())}</span>"
        )
    legend_html = "".join(legend_items)

    return f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>{html.escape(title)}</title>
  <style>
    body {{
      font-family: Arial, Helvetica, sans-serif;
      margin: 0;
      padding: 1rem;
      background: #f8f9fb;
    }}
    h1 {{
      font-size: 1.4rem;
      margin-bottom: 0.2rem;
    }}
    #graph-wrapper {{
      position: relative;
      background: #fff;
      padding: 1rem;
      border: 1px solid #d5d8dd;
      border-radius: 8px;
      overflow: auto;
    }}
    #columns {{
      display: flex;
      gap: 1rem;
      min-height: 200px;
    }}
    .column {{
      flex: 1;
      min-width: 160px;
    }}
    .column h2 {{
      font-size: 0.95rem;
      margin: 0 0 0.5rem 0;
      text-transform: uppercase;
      color: #4a4d57;
    }}
    .node-card {{
      border-radius: 6px;
      border: 1px solid #d5d8dd;
      padding: 0.6rem;
      margin-bottom: 0.6rem;
      background: #fff;
      box-shadow: 0 1px 2px rgba(0,0,0,0.05);
      position: relative;
    }}
    .node-card .symbol {{
      font-weight: bold;
      font-size: 0.9rem;
      display: block;
    }}
    .node-card .title {{
      font-size: 0.8rem;
      color: #444;
      margin-top: 0.2rem;
    }}
    .node-card .badge {{
      font-size: 0.7rem;
      color: #666;
      margin-top: 0.3rem;
      display: inline-block;
    }}
    svg#edges {{
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
    }}
    path.edge {{
      stroke: #8aa1c1;
      stroke-width: 2;
      fill: none;
      marker-end: url(#arrowhead);
      opacity: 0.85;
    }}
    .legend {{
      margin-bottom: 0.75rem;
    }}
    .legend-pill {{
      display: inline-flex;
      align-items: center;
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      padding: 0.15rem 0.45rem;
      border-radius: 999px;
      margin-right: 0.4rem;
      border: 1px solid #d5d8dd;
      color: #383c45;
    }}
    .node-card.type-agenda {{ border-color: #4284f5; }}
    .node-card.type-draft {{ border-color: #34a853; }}
    .node-card.type-committee_report {{ border-color: #fbbc05; }}
    .node-card.type-resolution {{ border-color: #ea4335; }}
    .node-card.type-meeting {{ border-color: #8e24aa; }}
    .node-card.missing {{
      opacity: 0.6;
      border-style: dashed;
    }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div class=\"legend\">{legend_html}</div>
  <div id=\"graph-wrapper\">
    <div id=\"columns\"></div>
    <svg id=\"edges\">
      <defs>
        <marker id=\"arrowhead\" markerWidth=\"8\" markerHeight=\"8\" refX=\"7\" refY=\"3.5\" orient=\"auto\">
          <polygon points=\"0 0, 8 3.5, 0 7\" fill=\"#8aa1c1\" />
        </marker>
      </defs>
    </svg>
  </div>
  <script>
    const GRAPH_DATA = {graph_json};
    const TYPE_ORDER = {json.dumps(GRAPH_DOC_TYPE_ORDER)};
    const GRAPH_DOC_TYPE_LABELS = {json.dumps(GRAPH_DOC_TYPE_LABELS)};

    function sanitizeId(value) {{
      return value ? value.replace(/[^0-9a-zA-Z_-]+/g, '_') : '';
    }}

    function renderGraph() {{
      const container = document.getElementById('columns');
      container.innerHTML = '';
      const availableTypes = Array.from(new Set([
        ...TYPE_ORDER,
        ...GRAPH_DATA.nodes.map(n => n.doc_type)
      ]));

      availableTypes.forEach(type => {{
        const nodes = GRAPH_DATA.nodes.filter(n => n.doc_type === type);
        if (!nodes.length) return;
        const column = document.createElement('div');
        column.className = 'column';
        const heading = document.createElement('h2');
        heading.textContent = (GRAPH_DOC_TYPE_LABELS[type] || type).toUpperCase();
        column.appendChild(heading);

        nodes.forEach(node => {{
          const card = document.createElement('div');
          const safeId = sanitizeId(node.id);
          card.id = `node-${{safeId}}`;
          card.className = `node-card type-${{type}}${{node.found ? '' : ' missing'}}`;
          card.dataset.nodeId = node.id;
          const symbol = document.createElement('span');
          symbol.className = 'symbol';
          symbol.textContent = node.symbol;
          const title = document.createElement('span');
          title.className = 'title';
          title.textContent = node.title || '';
          card.appendChild(symbol);
          card.appendChild(title);

          if (node.extra && (node.extra.item_number || node.extra.sub_item)) {{
            const badge = document.createElement('span');
            badge.className = 'badge';
            const itemLabel = `${{node.extra.item_number || ''}}${{node.extra.sub_item || ''}}`.trim();
            badge.textContent = itemLabel ? `Item ${{itemLabel}}` : '';
            card.appendChild(badge);
          }}

          column.appendChild(card);
        }});

        container.appendChild(column);
      }});

      requestAnimationFrame(drawEdges);
    }}

    function drawEdges() {{
      const wrapper = document.getElementById('graph-wrapper');
      const svg = document.getElementById('edges');
      const rect = wrapper.getBoundingClientRect();
      svg.setAttribute('width', rect.width);
      svg.setAttribute('height', rect.height);
      const defs = svg.querySelector('defs');
      const defsMarkup = defs ? defs.outerHTML : '';
      svg.innerHTML = defsMarkup;

      GRAPH_DATA.edges.forEach(edge => {{
        const srcEl = document.getElementById(`node-${{sanitizeId(edge.source)}}`);
        const tgtEl = document.getElementById(`node-${{sanitizeId(edge.target)}}`);
        if (!srcEl || !tgtEl) return;
        const srcRect = srcEl.getBoundingClientRect();
        const tgtRect = tgtEl.getBoundingClientRect();
        const wrapperRect = wrapper.getBoundingClientRect();
        const x1 = srcRect.right - wrapperRect.left;
        const y1 = srcRect.top + srcRect.height / 2 - wrapperRect.top;
        const x2 = tgtRect.left - wrapperRect.left;
        const y2 = tgtRect.top + tgtRect.height / 2 - wrapperRect.top;
        const controlOffset = Math.max(40, (x2 - x1) / 2);
        const d = `M ${{x1}} ${{y1}} C ${{x1 + controlOffset}} ${{y1}}, ${{x2 - controlOffset}} ${{y2}}, ${{x2}} ${{y2}}`;
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', d);
        path.setAttribute('class', 'edge');
        svg.appendChild(path);
      }});
    }}

    window.addEventListener('load', () => {{
      renderGraph();
      window.addEventListener('resize', () => requestAnimationFrame(drawEdges));
    }});
  </script>
</body>
</html>
"""

def main():
    parser = argparse.ArgumentParser(
        description="Trace UN document genealogy"
    )
    parser.add_argument(
        "symbol",
        help="Document symbol (e.g., A/RES/78/220, A/78/251, A/C.3/78/L.41)"
    )
    parser.add_argument(
        "--mode",
        choices=["backwards", "forwards", "draft"],
        help="Trace mode (default: auto-detect from symbol)"
    )
    parser.add_argument(
        "--item",
        help="Agenda item number for forwards mode (e.g., '71c')"
    )
    parser.add_argument(
        "--data-root",
        default=DEFAULT_PARSED_HTML,
        type=Path,
        help="Root directory for parsed HTML data"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show verbose output"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--graph-json",
        metavar="PATH",
        help="Write node-link graph JSON to PATH (use '-' for stdout)"
    )
    parser.add_argument(
        "--graph-mermaid",
        metavar="PATH",
        help="Write a Mermaid diagram description to PATH (use '-' for stdout)"
    )
    parser.add_argument(
        "--graph-html",
        metavar="PATH",
        help="Write a lightweight HTML preview to PATH"
    )

    args = parser.parse_args()

    # Build index
    print(f"Building document index from {args.data_root}...")
    index = UNDocumentIndex(args.data_root)
    print(f"Indexed {len(index.documents)} documents")

    # Auto-detect mode if not specified
    mode = args.mode
    if not mode:
        if "/RES/" in args.symbol.upper():
            mode = "backwards"
        elif "/L." in args.symbol.upper():
            mode = "draft"
        else:
            mode = "forwards"

    # Trace genealogy
    genealogy = DocumentGenealogy(index)
    if mode == "backwards":
        tree = genealogy.trace_backwards(args.symbol)
    elif mode == "forwards":
        tree = genealogy.trace_forwards(args.symbol, args.item)
    elif mode == "draft":
        tree = genealogy.trace_from_draft(args.symbol)

    graph_requested = any([args.graph_json, args.graph_mermaid, args.graph_html])
    graph_data = None
    if graph_requested and "error" not in tree:
        try:
            graph_data = build_graph_from_tree(tree)
        except ValueError as exc:
            print(f"Warning: {exc}")
    elif graph_requested and "error" in tree:
        print("Graph output skipped because the document trace returned an error.")

    # Output
    graph_to_stdout = args.graph_json == '-' or args.graph_mermaid == '-' or args.graph_html == '-'

    should_print_tree = not args.json and (not graph_to_stdout or "error" in tree)

    if args.json:
        print(json.dumps(tree, indent=2, default=str))
    elif should_print_tree:
        genealogy.print_tree(tree, verbose=args.verbose)

    def write_output(path_str: Optional[str], content: str, description: str):
        if not path_str:
            return
        if path_str == '-':
            print(content)
            return
        output_path = Path(path_str)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content)
        print(f"Wrote {description} to {output_path}")

    if args.graph_json and graph_data:
        write_output(args.graph_json, json.dumps(graph_data, indent=2), "graph JSON")

    if args.graph_mermaid and graph_data:
        mermaid = graph_to_mermaid(graph_data)
        write_output(args.graph_mermaid, mermaid, "Mermaid diagram")

    if args.graph_html and graph_data:
        html_doc = graph_to_html(graph_data, title=f"Genealogy for {args.symbol}")
        write_output(args.graph_html, html_doc, "HTML preview")


if __name__ == "__main__":
    main()
