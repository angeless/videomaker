"""Tag manager mixin for GlobalMediaLibrary.

Extracted from global_media_library.py — contains tag tree navigation,
tag search, evidence chain retrieval, custom tag CRUD, and user feedback.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TagManagerMixin:
    """Methods related to tag CRUD, evidence chains, and user feedback."""

    def _table_exists(self, conn, table_name: str) -> bool:
        """Check if a table exists in the database."""
        r = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return r[0] > 0

    # ── Phase 3: tag tree, tag search, evidence chain ──

    def get_tag_tree(self) -> List[Dict]:
        """Return tag_category grouped view of all active tags.

        Returns list of category dicts, each containing tags with asset counts.
        Frontend reads len(result) for category count — never hardcode.
        """
        with self._connect() as conn:
            cats = conn.execute(
                "SELECT category_id, category_name, category_code FROM tag_category ORDER BY sort_order, category_id"
            ).fetchall()
            result = []
            for cat in cats:
                cat_id = cat[0]
                tags = conn.execute(
                    """SELECT t.tag_id, t.tag_name, t.semantic_slot,
                              (SELECT COUNT(DISTINCT atr.asset_id) FROM asset_tag_result atr
                               WHERE atr.tag_id = t.tag_id AND atr.result_scope='asset' AND atr.is_displayed=1) AS asset_count
                       FROM tag t
                       WHERE t.category_id = ? AND t.is_active = 1
                       ORDER BY t.tag_name""",
                    (cat_id,),
                ).fetchall()
                result.append({
                    "category_id": cat_id,
                    "category_name": cat[1],
                    "category_code": cat[2],
                    "tag_count": len(tags),
                    "tags": [
                        {
                            "tag_id": t[0],
                            "tag_name": t[1],
                            "semantic_slot": t[2],
                            "asset_count": t[3],
                        }
                        for t in tags
                    ],
                })
            return result

    def search_tags(self, q: str, limit: int = 20) -> List[Dict]:
        """Autocomplete: search tag_name + alias + custom_tag.

        Dedup key: (tag_id, matched_via). Same tag can appear for both tag_name and alias hits.
        """
        if not q or not q.strip():
            return []
        normalized = q.strip().lower()
        results: List[Dict] = []
        seen: set = set()

        with self._connect() as conn:
            # tag_name matches
            tag_rows = conn.execute(
                """SELECT t.tag_id, t.tag_name, tc.category_name, t.semantic_slot
                   FROM tag t
                   LEFT JOIN tag_category tc ON t.category_id = tc.category_id
                   WHERE t.is_active = 1 AND t.normalized_name LIKE ?
                   ORDER BY t.tag_name LIMIT ?""",
                (f"%{normalized}%", limit),
            ).fetchall()
            for r in tag_rows:
                key = (r[0], "tag_name")
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "tag_id": r[0], "tag_name": r[1],
                        "category_name": r[2], "semantic_slot": r[3],
                        "matched_via": "tag_name", "matched_text": r[1],
                    })

            # alias matches
            alias_rows = conn.execute(
                """SELECT ta.tag_id, t.tag_name, tc.category_name, t.semantic_slot, ta.alias_name
                   FROM tag_alias ta
                   JOIN tag t ON ta.tag_id = t.tag_id AND t.is_active = 1
                   LEFT JOIN tag_category tc ON t.category_id = tc.category_id
                   WHERE ta.normalized_alias LIKE ?
                   ORDER BY ta.alias_name LIMIT ?""",
                (f"%{normalized}%", limit),
            ).fetchall()
            for r in alias_rows:
                key = (r[0], "alias")
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "tag_id": r[0], "tag_name": r[1],
                        "category_name": r[2], "semantic_slot": r[3],
                        "matched_via": "alias", "matched_text": r[4],
                    })

            # custom_tag matches (LEFT JOIN so custom tags without parent are included)
            custom_rows = conn.execute(
                """SELECT ct.custom_tag_id, ct.parent_system_tag_id,
                          t.tag_name, tc.category_name, t.semantic_slot,
                          ct.custom_tag_name, ct.semantic_slot AS ct_slot
                   FROM custom_tag ct
                   LEFT JOIN tag t ON ct.parent_system_tag_id = t.tag_id AND t.is_active = 1
                   LEFT JOIN tag_category tc ON t.category_id = tc.category_id
                   WHERE ct.normalized_name LIKE ? AND ct.status != 'archived'
                   ORDER BY ct.custom_tag_name LIMIT ?""",
                (f"%{normalized}%", limit),
            ).fetchall()
            for r in custom_rows:
                ct_id = r[0]
                parent_tag_id = r[1]
                key = (f"ct_{ct_id}", "custom_tag")
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "tag_id": parent_tag_id,
                        "custom_tag_id": ct_id,
                        "tag_name": r[2] or r[5],  # parent tag_name or custom_tag_name
                        "category_name": r[3],
                        "semantic_slot": r[4] or r[6],  # parent slot or custom slot
                        "matched_via": "custom_tag",
                        "matched_text": r[5],  # custom_tag_name
                    })

        # Sort: tag_name > alias > custom_tag
        priority = {"tag_name": 0, "alias": 1, "custom_tag": 2}
        results.sort(key=lambda x: priority.get(x["matched_via"], 9))
        return results[:limit]

    def get_evidence_chain(self, asset_id: str, tag_id: Optional[int] = None) -> Dict:
        """Return structured evidence chain for an asset.

        Returns tag_results + evidence in minimal structured format.
        """
        with self._connect() as conn:
            # Tag results
            atr_sql = """
                SELECT atr.tag_id, t.tag_name, atr.source_summary, atr.decision_reason,
                       atr.base_score, atr.source_bonus, atr.cooccurrence_bonus,
                       atr.hierarchy_bonus, atr.conflict_penalty, atr.negative_penalty,
                       atr.final_score, atr.user_adjustment, atr.effective_score,
                       atr.confidence_band, atr.user_confirm_state
                FROM asset_tag_result atr
                JOIN tag t ON atr.tag_id = t.tag_id
                WHERE atr.asset_id = ? AND atr.result_scope = 'asset'
            """
            atr_params: list = [asset_id]
            if tag_id is not None:
                atr_sql += " AND atr.tag_id = ?"
                atr_params.append(tag_id)
            atr_sql += " ORDER BY atr.effective_score DESC"

            atr_rows = conn.execute(atr_sql, atr_params).fetchall()
            tag_results = []
            for r in atr_rows:
                decision_reason = r[3]
                if isinstance(decision_reason, str):
                    try:
                        decision_reason = json.loads(decision_reason)
                    except Exception:
                        decision_reason = [decision_reason] if decision_reason else []
                tag_results.append({
                    "tag_id": r[0],
                    "tag_name": r[1],
                    "source_summary": r[2],
                    "decision_reason": decision_reason or [],
                    "score_breakdown": {
                        "base_score": r[4],
                        "source_bonus": r[5],
                        "cooccurrence_bonus": r[6],
                        "hierarchy_bonus": r[7],
                        "conflict_penalty": r[8],
                        "negative_penalty": r[9],
                        "final_score": r[10],
                        "user_adjustment": r[11],
                        "effective_score": r[12],
                    },
                    "confidence_band": r[13],
                    "user_confirm_state": r[14],
                })

            # Evidence
            ev_sql = """
                SELECT source_kind, source_model, raw_value, base_score, weighted_score,
                       tag_id, semantic_slot
                FROM evidence
                WHERE asset_id = ?
            """
            ev_params: list = [asset_id]
            if tag_id is not None:
                ev_sql += " AND tag_id = ?"
                ev_params.append(tag_id)
            ev_sql += " ORDER BY weighted_score DESC LIMIT 100"

            ev_rows = conn.execute(ev_sql, ev_params).fetchall()
            evidence_list = []
            for e in ev_rows:
                evidence_list.append({
                    "source_kind": e[0],
                    "source_model": e[1],
                    "raw_value": e[2],
                    "base_score": e[3],
                    "weighted_score": e[4],
                    "tag_id": e[5],
                    "semantic_slot": e[6],
                })

            return {
                "asset_id": asset_id,
                "tag_results": tag_results,
                "evidence_list": evidence_list,
                "total_tag_results": len(tag_results),
                "total_evidence": len(evidence_list),
            }

    # ────────────────────────────────────────────────
    # Phase 5: Custom Tag CRUD
    # ────────────────────────────────────────────────

    def create_custom_tag(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new custom tag. Returns the created tag record."""
        name = str(data.get("custom_tag_name", "")).strip()
        if not name:
            return {"error": "custom_tag_name is required"}

        normalized = name.lower().strip()
        now = self._now()

        with self._connect() as conn:
            # Check duplicate
            existing = conn.execute(
                "SELECT custom_tag_id FROM custom_tag WHERE normalized_name = ? AND status != 'archived'",
                (normalized,),
            ).fetchone()
            if existing:
                return {"error": f"Custom tag '{name}' already exists", "custom_tag_id": existing[0]}

            # Resolve parent system tag if specified
            parent_tag_id = None
            parent_name = str(data.get("parent_tag_name", "")).strip()
            if parent_name:
                row = conn.execute(
                    "SELECT tag_id FROM tag WHERE tag_name = ? AND is_active = 1", (parent_name,)
                ).fetchone()
                if row:
                    parent_tag_id = row[0]

            conn.execute(
                """INSERT INTO custom_tag
                   (user_id, custom_tag_name, normalized_name, parent_system_tag_id,
                    category_id, semantic_slot, aliases, related_objects,
                    trigger_texts, negative_terms, composite_logic,
                    threshold_value, status, match_count, last_used_at,
                    created_at, updated_at)
                   VALUES (?,?,?,?, ?,?,?,?, ?,?,?, ?,?,0,NULL, ?,?)""",
                (
                    int(data.get("user_id", 0)),
                    name,
                    normalized,
                    parent_tag_id,
                    data.get("category_id"),
                    data.get("semantic_slot"),
                    data.get("aliases"),
                    data.get("related_objects"),
                    data.get("trigger_texts"),
                    data.get("negative_terms"),
                    data.get("composite_logic"),
                    float(data.get("threshold_value", 0.72)),
                    "active",
                    now,
                    now,
                ),
            )
            ct_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.commit()

        return self._get_custom_tag_detail(ct_id)

    def list_custom_tags(self, include_archived: bool = False) -> List[Dict[str, Any]]:
        """List all custom tags."""
        with self._connect() as conn:
            sql = """SELECT ct.custom_tag_id, ct.custom_tag_name, ct.normalized_name,
                            ct.parent_system_tag_id, ct.aliases, ct.trigger_texts,
                            ct.negative_terms, ct.composite_logic,
                            ct.status, ct.match_count, ct.last_used_at,
                            ct.created_at, ct.updated_at,
                            t.tag_name AS parent_tag_name
                     FROM custom_tag ct
                     LEFT JOIN tag t ON ct.parent_system_tag_id = t.tag_id"""
            if not include_archived:
                sql += " WHERE ct.status != 'archived'"
            sql += " ORDER BY ct.updated_at DESC"
            rows = conn.execute(sql).fetchall()
            return [
                {
                    "custom_tag_id": r[0],
                    "custom_tag_name": r[1],
                    "normalized_name": r[2],
                    "parent_system_tag_id": r[3],
                    "aliases": r[4],
                    "trigger_texts": r[5],
                    "negative_terms": r[6],
                    "composite_logic": r[7],
                    "status": r[8],
                    "match_count": r[9],
                    "last_used_at": r[10],
                    "created_at": r[11],
                    "updated_at": r[12],
                    "parent_tag_name": r[13],
                }
                for r in rows
            ]

    def update_custom_tag(self, custom_tag_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a custom tag by ID. Returns updated record."""
        now = self._now()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT custom_tag_id FROM custom_tag WHERE custom_tag_id = ?", (custom_tag_id,)
            ).fetchone()
            if not existing:
                return {"error": f"Custom tag {custom_tag_id} not found"}

            updates = []
            params = []

            if "custom_tag_name" in data:
                name = str(data["custom_tag_name"]).strip()
                if name:
                    updates.extend(["custom_tag_name = ?", "normalized_name = ?"])
                    params.extend([name, name.lower().strip()])

            for field in ("aliases", "trigger_texts", "negative_terms", "composite_logic",
                          "semantic_slot", "related_objects"):
                if field in data:
                    updates.append(f"{field} = ?")
                    params.append(data[field])

            if "threshold_value" in data:
                updates.append("threshold_value = ?")
                params.append(float(data["threshold_value"]))

            if "status" in data and data["status"] in ("active", "gray", "archived"):
                updates.append("status = ?")
                params.append(data["status"])

            if "parent_tag_name" in data:
                parent_name = str(data["parent_tag_name"]).strip()
                if parent_name:
                    row = conn.execute(
                        "SELECT tag_id FROM tag WHERE tag_name = ? AND is_active = 1", (parent_name,)
                    ).fetchone()
                    updates.append("parent_system_tag_id = ?")
                    params.append(row[0] if row else None)
                else:
                    updates.append("parent_system_tag_id = ?")
                    params.append(None)

            if not updates:
                return {"error": "No valid fields to update"}

            updates.append("updated_at = ?")
            params.append(now)
            params.append(custom_tag_id)

            conn.execute(
                f"UPDATE custom_tag SET {', '.join(updates)} WHERE custom_tag_id = ?",
                params,
            )
            conn.commit()

        return self._get_custom_tag_detail(custom_tag_id)

    def archive_custom_tag(self, custom_tag_id: int) -> Dict[str, Any]:
        """Soft-delete a custom tag by setting status to 'archived'."""
        now = self._now()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT custom_tag_id, status FROM custom_tag WHERE custom_tag_id = ?",
                (custom_tag_id,),
            ).fetchone()
            if not existing:
                return {"error": f"Custom tag {custom_tag_id} not found"}
            if existing[1] == "archived":
                return {"ok": True, "message": "Already archived"}

            conn.execute(
                "UPDATE custom_tag SET status = 'archived', updated_at = ? WHERE custom_tag_id = ?",
                (now, custom_tag_id),
            )
            conn.commit()
        return {"ok": True, "custom_tag_id": custom_tag_id}

    def _get_custom_tag_detail(self, custom_tag_id: int) -> Dict[str, Any]:
        """Get single custom tag detail."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT ct.custom_tag_id, ct.custom_tag_name, ct.normalized_name,
                          ct.parent_system_tag_id, ct.aliases, ct.trigger_texts,
                          ct.negative_terms, ct.composite_logic,
                          ct.threshold_value, ct.status, ct.match_count,
                          ct.last_used_at, ct.created_at, ct.updated_at,
                          t.tag_name AS parent_tag_name
                   FROM custom_tag ct
                   LEFT JOIN tag t ON ct.parent_system_tag_id = t.tag_id
                   WHERE ct.custom_tag_id = ?""",
                (custom_tag_id,),
            ).fetchone()
            if not row:
                return {"error": f"Custom tag {custom_tag_id} not found"}
            return {
                "custom_tag_id": row[0],
                "custom_tag_name": row[1],
                "normalized_name": row[2],
                "parent_system_tag_id": row[3],
                "aliases": row[4],
                "trigger_texts": row[5],
                "negative_terms": row[6],
                "composite_logic": row[7],
                "threshold_value": row[8],
                "status": row[9],
                "match_count": row[10],
                "last_used_at": row[11],
                "created_at": row[12],
                "updated_at": row[13],
                "parent_tag_name": row[14],
            }

    # ────────────────────────────────────────────────
    # Phase 5: Feedback API
    # ────────────────────────────────────────────────

    def submit_feedback(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit user feedback on an asset-tag pair.

        Supported feedback_type:
          - confirm_correct: user agrees with a tag (user_confirm_state → 'confirmed')
          - reject_wrong: user disagrees (user_confirm_state → 'rejected', user_adjustment -= penalty)
          - add_missing: user proposes a tag the system missed
          - remove_irrelevant: user marks tag as irrelevant (user_confirm_state → 'rejected')

        Rules:
          - feedback_event is ALWAYS appended (immutable log).
          - final_score is NEVER modified.
          - Only user_adjustment and user_confirm_state are updated.
          - effective_score = final_score + user_adjustment.
        """
        asset_id = str(data.get("asset_id", "")).strip()
        feedback_type = str(data.get("feedback_type", "")).strip()
        note = str(data.get("note", "")).strip()

        if not asset_id:
            return {"error": "asset_id is required"}
        if feedback_type not in ("confirm_correct", "reject_wrong", "add_missing", "remove_irrelevant"):
            return {"error": f"Invalid feedback_type: {feedback_type}"}

        tag_id = data.get("tag_id")
        custom_tag_id = data.get("custom_tag_id")
        tag_name = str(data.get("tag_name", "")).strip()
        now = self._now()

        with self._connect() as conn:
            # Resolve tag_id from tag_name if not given directly
            if tag_id is None and tag_name:
                row = conn.execute(
                    "SELECT tag_id FROM tag WHERE tag_name = ? AND is_active = 1", (tag_name,)
                ).fetchone()
                if row:
                    tag_id = row[0]

            # 1. Always record the feedback event (immutable log)
            conn.execute(
                """INSERT INTO feedback_event
                   (user_id, asset_id, segment_id, tag_id, custom_tag_id,
                    feedback_type, note, created_at)
                   VALUES (?,?,NULL,?,?, ?,?,?)""",
                (
                    int(data.get("user_id", 0)),
                    asset_id,
                    tag_id,
                    custom_tag_id,
                    feedback_type,
                    note,
                    now,
                ),
            )

            result = {"ok": True, "feedback_type": feedback_type, "asset_id": asset_id}

            # 2. Apply effect based on type
            if feedback_type == "confirm_correct" and tag_id is not None:
                conn.execute(
                    """UPDATE asset_tag_result
                       SET user_confirm_state = 'confirmed',
                           user_adjustment = MAX(user_adjustment, 0.05),
                           effective_score = final_score + MAX(user_adjustment, 0.05),
                           updated_at = ?
                       WHERE asset_id = ? AND tag_id = ? AND result_scope = 'asset'""",
                    (now, asset_id, tag_id),
                )
                result["confirm_state"] = "confirmed"

            elif feedback_type == "reject_wrong" and tag_id is not None:
                conn.execute(
                    """UPDATE asset_tag_result
                       SET user_confirm_state = 'rejected',
                           user_adjustment = MIN(user_adjustment, -0.30),
                           effective_score = final_score + MIN(user_adjustment, -0.30),
                           updated_at = ?
                       WHERE asset_id = ? AND tag_id = ? AND result_scope = 'asset'""",
                    (now, asset_id, tag_id),
                )
                result["confirm_state"] = "rejected"

            elif feedback_type == "remove_irrelevant" and tag_id is not None:
                conn.execute(
                    """UPDATE asset_tag_result
                       SET user_confirm_state = 'rejected',
                           user_adjustment = -1.0,
                           effective_score = final_score - 1.0,
                           is_displayed = 0,
                           updated_at = ?
                       WHERE asset_id = ? AND tag_id = ? AND result_scope = 'asset'""",
                    (now, asset_id, tag_id),
                )
                result["confirm_state"] = "rejected"
                result["is_displayed"] = False

            elif feedback_type == "add_missing":
                # User says this asset should have a tag it currently lacks.
                # Create asset_tag_result with user-origin score.
                if tag_id is not None:
                    existing = conn.execute(
                        """SELECT result_id FROM asset_tag_result
                           WHERE asset_id = ? AND tag_id = ? AND result_scope = 'asset'""",
                        (asset_id, tag_id),
                    ).fetchone()
                    if existing:
                        # Already exists — just confirm
                        conn.execute(
                            """UPDATE asset_tag_result
                               SET user_confirm_state = 'confirmed',
                                   user_adjustment = MAX(user_adjustment, 0.10),
                                   effective_score = final_score + MAX(user_adjustment, 0.10),
                                   is_displayed = 1,
                                   updated_at = ?
                               WHERE asset_id = ? AND tag_id = ? AND result_scope = 'asset'""",
                            (now, asset_id, tag_id),
                        )
                    else:
                        # New — user-created tag result
                        conn.execute(
                            """INSERT INTO asset_tag_result
                               (asset_id, tag_id, result_scope, is_displayed,
                                base_score, final_score, user_adjustment, effective_score,
                                confidence_band, source_summary, decision_reason,
                                user_confirm_state, created_at, updated_at)
                               VALUES (?,?,'asset',1,
                                       0.0, 0.0, 0.50, 0.50,
                                       'user','user_feedback','user added missing tag',
                                       'confirmed',?,?)""",
                            (asset_id, tag_id, now, now),
                        )
                    result["tag_id"] = tag_id
                    result["confirm_state"] = "confirmed"

            conn.commit()
            return result

    def get_feedback_history(self, asset_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get feedback events for an asset."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT fe.feedback_id, fe.asset_id, fe.tag_id, fe.custom_tag_id,
                          fe.feedback_type, fe.note, fe.created_at,
                          t.tag_name
                   FROM feedback_event fe
                   LEFT JOIN tag t ON fe.tag_id = t.tag_id
                   WHERE fe.asset_id = ?
                   ORDER BY fe.created_at DESC
                   LIMIT ?""",
                (asset_id, limit),
            ).fetchall()
            return [
                {
                    "feedback_id": r[0],
                    "asset_id": r[1],
                    "tag_id": r[2],
                    "custom_tag_id": r[3],
                    "feedback_type": r[4],
                    "note": r[5],
                    "created_at": r[6],
                    "tag_name": r[7],
                }
                for r in rows
            ]
