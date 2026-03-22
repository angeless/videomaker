"""Auto-tagger mixin for GlobalMediaLibrary.

Extracted from global_media_library.py — contains learning candidates
management, auto-classification, candidate promotion, and library health.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependency; resolved at first use.
_TAG_CATEGORY_TO_SLOT = None


def _get_tag_category_to_slot():
    global _TAG_CATEGORY_TO_SLOT
    if _TAG_CATEGORY_TO_SLOT is None:
        from modules.library.global_media_library import _TAG_CATEGORY_TO_SLOT as _m
        _TAG_CATEGORY_TO_SLOT = _m
    return _TAG_CATEGORY_TO_SLOT


class AutoTaggerMixin:
    """Methods related to learning candidates and library health monitoring."""

    def get_learning_candidates(self, source_kind: str = None, status: str = "pending", limit: int = 50) -> List[Dict]:
        """Return learning candidates, optionally filtered by source_kind and review_status."""
        with self._connect() as conn:
            conditions = []
            params: list = []
            if source_kind:
                conditions.append("source_kind = ?")
                params.append(source_kind)
            if status:
                conditions.append("review_status = ?")
                params.append(status)
            where = " AND ".join(conditions) if conditions else "1=1"
            params.append(limit)
            rows = conn.execute(
                f"""SELECT candidate_id, candidate_text, normalized_text, category_hint,
                           source_kind, occurrence_count, asset_count, confirmed_count,
                           suggested_action, review_status, blocked_reason, created_at,
                           cooccur_json
                    FROM learning_candidate
                    WHERE {where}
                    ORDER BY occurrence_count DESC
                    LIMIT ?""",
                tuple(params),
            ).fetchall()
            return [
                {
                    "candidate_id": r[0], "candidate_text": r[1], "normalized": r[2],
                    "category_hint": r[3], "source_kind": r[4],
                    "occurrence_count": r[5], "asset_count": r[6],
                    "confirmed_count": r[7], "suggested_action": r[8],
                    "review_status": r[9], "blocked_reason": r[10],
                    "first_seen": r[11], "cooccur_json": r[12],
                }
                for r in rows
            ]

    def review_learning_candidate(self, candidate_id: int, action: str, reviewed_by: str = "user") -> Dict:
        """Review a learning candidate: approve, reject, or block.

        Args:
            candidate_id: The candidate to review.
            action: One of 'approve', 'reject', 'block'.
            reviewed_by: Who reviewed it.
        """
        if action not in ("approve", "reject", "block"):
            return {"error": f"Invalid action: {action}. Must be approve/reject/block."}

        status_map = {"approve": "approved", "reject": "rejected", "block": "blocked"}
        new_status = status_map[action]

        with self._connect() as conn:
            row = conn.execute(
                "SELECT candidate_id, candidate_text, normalized_text FROM learning_candidate WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            if not row:
                return {"error": f"Candidate {candidate_id} not found."}

            now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            conn.execute(
                """UPDATE learning_candidate
                   SET review_status = ?, reviewed_by = ?, reviewed_at = ?
                   WHERE candidate_id = ?""",
                (new_status, reviewed_by, now, candidate_id),
            )

            # If blocked, also add to learning_stopword
            if action == "block":
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO learning_stopword
                           (normalized_text, block_reason, blocked_by)
                           VALUES (?, 'user_blocked', ?)""",
                        (row[2], reviewed_by),
                    )
                except Exception:
                    pass

            conn.commit()
            return {"ok": True, "candidate_id": candidate_id, "new_status": new_status}

    def classify_learning_candidates(self, limit: int = 200) -> Dict:
        """Analyze pending learning candidates and auto-classify suggested_action + cooccur_json.

        Classification logic (from Design Note 4):
          merge_to_alias  — co-occurrence rate >= 0.7 with an existing tag + semantic overlap
          upgrade_to_new_tag — belongs to a known category + occurs in >= 5 assets + high stability
          become_rule_trigger — co-occurs strongly with 2+ tags in fixed patterns
          reject_noise — short/numeric/single-char/low-info patterns

        Returns summary dict with counts per action.
        """
        import re as _re_mod

        # ── Noise patterns (cheap, run first) ──
        _NOISE_RX = _re_mod.compile(
            r"^[\d\s\.\-:_/\\]+$"          # pure numeric / timestamp / path fragments
            r"|^[a-zA-Z]{1,2}$"             # single/double ascii chars
            r"|^\w{1,1}$"                   # single unicode char
            r"|^(img|dsc|mov|mp4|jpg|png|heic|aac|wav)[_\-]?\d*$"  # filename fragments
            r"|^https?://"                  # URLs
            r"|^\d{2,4}[\-/]\d{1,2}[\-/]\d{1,2}"  # date patterns
            r"|^[\u2000-\u206f\u2190-\u21ff\u25a0-\u25ff\u2600-\u26ff]"  # symbol-heavy
            , _re_mod.IGNORECASE
        )
        _FILLER_WORDS = {
            "嗯", "啊", "哦", "呃", "哈", "嘛", "吧", "呀", "喂", "哎",
            "那个", "就是", "然后", "这个", "所以", "其实", "可能", "应该",
            "加载中", "请稍候", "版权所有", "立即购买", "限时优惠",
            "点击查看", "关注我", "转发", "评论", "点赞",
        }

        with self._connect() as conn:
            # Fetch pending candidates
            rows = conn.execute(
                """SELECT candidate_id, candidate_text, normalized_text,
                          category_hint, source_kind, occurrence_count, asset_count
                   FROM learning_candidate
                   WHERE review_status = 'pending'
                   ORDER BY occurrence_count DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()

            if not rows:
                return {"classified": 0, "actions": {}}

            # Pre-load existing tag names and aliases for co-occurrence matching
            all_tags = {}
            for r in conn.execute("SELECT tag_id, normalized_name, tag_name FROM tag WHERE is_active = 1").fetchall():
                all_tags[r[1]] = {"tag_id": r[0], "tag_name": r[2]}
            all_aliases = {}
            for r in conn.execute(
                "SELECT a.normalized_alias, a.tag_id, t.tag_name FROM tag_alias a "
                "JOIN tag t ON a.tag_id = t.tag_id WHERE t.is_active = 1"
            ).fetchall():
                all_aliases[r[0]] = {"tag_id": r[1], "tag_name": r[2]}

            counts = {"merge_to_alias": 0, "upgrade_to_new_tag": 0,
                       "become_rule_trigger": 0, "reject_noise": 0, "review": 0}

            for row in rows:
                cid, text, norm, cat_hint, source, occ, assets = (
                    row[0], row[1], row[2], row[3], row[4], row[5], row[6],
                )
                action = "review"
                cooccur = {}

                # ── Step 1: Noise detection ──
                if (norm in _FILLER_WORDS
                    or _NOISE_RX.match(norm)
                    or len(norm) <= 1):
                    action = "reject_noise"
                else:
                    # ── Step 2: Substring / near-match with existing tags → merge_to_alias ──
                    best_match = None
                    best_score = 0.0
                    for tag_norm, tag_info in all_tags.items():
                        # Exact substring check (candidate is substring of tag or vice versa)
                        if len(norm) >= 2 and len(tag_norm) >= 2:
                            if norm in tag_norm or tag_norm in norm:
                                overlap = min(len(norm), len(tag_norm)) / max(len(norm), len(tag_norm))
                                if overlap > best_score and overlap >= 0.5:
                                    best_score = overlap
                                    best_match = tag_info
                    # Also check aliases
                    for alias_norm, alias_info in all_aliases.items():
                        if len(norm) >= 2 and len(alias_norm) >= 2:
                            if norm in alias_norm or alias_norm in norm:
                                overlap = min(len(norm), len(alias_norm)) / max(len(norm), len(alias_norm))
                                if overlap > best_score and overlap >= 0.5:
                                    best_score = overlap
                                    best_match = alias_info

                    if best_match and best_score >= 0.6:
                        action = "merge_to_alias"
                        cooccur = {"merge_target_tag_id": best_match["tag_id"],
                                   "merge_target_name": best_match["tag_name"],
                                   "similarity": round(best_score, 2)}

                    # ── Step 3: Co-occurrence analysis with asset_tag_result ──
                    elif source == "llm" and assets >= 3:
                        # Find which existing tags co-occur with this candidate in the same assets
                        # Look at assets where this candidate's source term appears in semantic_json
                        cooccur_tags = conn.execute(
                            """SELECT atr.tag_id, t.tag_name, COUNT(*) as co_count
                               FROM asset_tag_result atr
                               JOIN tag t ON atr.tag_id = t.tag_id
                               WHERE atr.asset_id IN (
                                   SELECT e.asset_id FROM evidence e
                                   WHERE e.raw_value = ? AND e.source_kind = 'llm'
                               )
                               AND atr.is_displayed = 1
                               GROUP BY atr.tag_id
                               ORDER BY co_count DESC
                               LIMIT 10""",
                            (text,),
                        ).fetchall()

                        if cooccur_tags:
                            cooccur = {
                                "cooccurring_tags": [
                                    {"tag_id": r[0], "tag_name": r[1], "count": r[2]}
                                    for r in cooccur_tags[:5]
                                ]
                            }
                            # If high co-occurrence with 2+ tags → rule trigger candidate
                            if len(cooccur_tags) >= 2 and cooccur_tags[0][2] >= 3:
                                action = "become_rule_trigger"
                            # Has known category + enough assets → upgrade candidate
                            elif cat_hint and cat_hint != "search" and assets >= 5 and occ >= 10:
                                action = "upgrade_to_new_tag"

                    # ── Step 4: Fallback heuristics for upgrade ──
                    if action == "review" and cat_hint and cat_hint != "search":
                        if assets >= 5 and occ >= 15:
                            action = "upgrade_to_new_tag"

                # Write classification result
                try:
                    cooccur_str = json.dumps(cooccur, ensure_ascii=False) if cooccur else None
                    conn.execute(
                        """UPDATE learning_candidate
                           SET suggested_action = ?, cooccur_json = ?
                           WHERE candidate_id = ?""",
                        (action, cooccur_str, cid),
                    )
                except Exception:
                    pass

                counts[action] = counts.get(action, 0) + 1

            conn.commit()
            return {
                "classified": len(rows),
                "actions": counts,
            }

    def promote_candidate(self, candidate_id: int, reviewed_by: str = "user") -> Dict:
        """Promote an approved learning candidate into the tag system.

        Based on suggested_action:
          merge_to_alias  → create tag_alias pointing to the merge target
          upgrade_to_new_tag → create a new tag entry
          become_rule_trigger → (future) create composite_rule; for now just approve
          reject_noise → add to learning_stopword

        Returns result dict with the action taken.
        """
        with self._connect() as conn:
            row = conn.execute(
                """SELECT candidate_id, candidate_text, normalized_text,
                          category_hint, source_kind, suggested_action, cooccur_json,
                          review_status
                   FROM learning_candidate WHERE candidate_id = ?""",
                (candidate_id,),
            ).fetchone()
            if not row:
                return {"error": f"Candidate {candidate_id} not found."}

            cid, text, norm, cat_hint, source, action, cooccur_raw, status = (
                row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7],
            )

            if status in ("blocked",):
                return {"error": f"Candidate {cid} is already blocked."}

            now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            result_info = {"candidate_id": cid, "candidate_text": text, "action": action}

            if action == "merge_to_alias":
                # Parse cooccur_json to find merge target
                target_tag_id = None
                if cooccur_raw:
                    try:
                        cooccur = json.loads(cooccur_raw)
                        target_tag_id = cooccur.get("merge_target_tag_id")
                    except Exception:
                        pass
                if not target_tag_id:
                    return {"error": "No merge target found in cooccur_json. Run classify first."}

                # Check target tag exists
                target = conn.execute(
                    "SELECT tag_id, tag_name FROM tag WHERE tag_id = ? AND is_active = 1",
                    (target_tag_id,),
                ).fetchone()
                if not target:
                    return {"error": f"Target tag {target_tag_id} not found or inactive."}

                # Check alias doesn't already exist
                existing = conn.execute(
                    "SELECT alias_id FROM tag_alias WHERE tag_id = ? AND normalized_alias = ?",
                    (target_tag_id, norm),
                ).fetchone()
                if existing:
                    result_info["note"] = "Alias already exists"
                else:
                    conn.execute(
                        """INSERT INTO tag_alias
                           (tag_id, alias_name, normalized_alias, alias_type,
                            source_type, confidence)
                           VALUES (?, ?, ?, 'alias', 'learned', 0.9)""",
                        (target_tag_id, text, norm),
                    )
                    result_info["created_alias"] = text
                    result_info["target_tag_name"] = target[1]

                # Mark as promoted
                conn.execute(
                    """UPDATE learning_candidate
                       SET review_status = 'approved', suggested_action = 'merge_to_alias',
                           reviewed_by = ?, reviewed_at = ?
                       WHERE candidate_id = ?""",
                    (reviewed_by, now, cid),
                )

            elif action == "upgrade_to_new_tag":
                # Resolve category_id and semantic_slot from category_hint
                slot = _get_tag_category_to_slot().get(cat_hint, "object") if cat_hint else "object"
                cat_row = conn.execute(
                    "SELECT category_id, category_code FROM tag_category WHERE category_code = ? LIMIT 1",
                    (slot,),
                ).fetchone()
                if not cat_row:
                    # Fallback: find any active category that matches the slot
                    cat_row = conn.execute(
                        """SELECT tc.category_id, tc.category_code FROM tag_category tc
                           JOIN tag t ON t.category_id = tc.category_id
                           WHERE t.semantic_slot = ? AND tc.is_active = 1
                           LIMIT 1""",
                        (slot,),
                    ).fetchone()
                if not cat_row:
                    # Last resort: use first active category
                    cat_row = conn.execute(
                        "SELECT category_id, category_code FROM tag_category WHERE is_active = 1 ORDER BY sort_order LIMIT 1"
                    ).fetchone()

                category_id = cat_row[0]
                cat_code = cat_row[1]

                # Generate unique tag_code
                max_code = conn.execute(
                    "SELECT MAX(CAST(SUBSTR(tag_code, LENGTH(?) + 2) AS INTEGER)) FROM tag WHERE tag_code LIKE ?",
                    (cat_code, f"{cat_code}_%"),
                ).fetchone()[0]
                next_num = (max_code or 0) + 1
                tag_code = f"{cat_code}_{next_num:04d}"

                # Check for duplicate
                existing = conn.execute(
                    "SELECT tag_id FROM tag WHERE normalized_name = ? AND category_id = ?",
                    (norm, category_id),
                ).fetchone()
                if existing:
                    result_info["note"] = f"Tag already exists (tag_id={existing[0]})"
                else:
                    conn.execute(
                        """INSERT INTO tag
                           (tag_name, normalized_name, tag_code, category_id,
                            semantic_slot, source_type, is_active)
                           VALUES (?, ?, ?, ?, ?, 'learned', 1)""",
                        (text, norm, tag_code, category_id, slot),
                    )
                    new_tag_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    result_info["created_tag_id"] = new_tag_id
                    result_info["tag_code"] = tag_code
                    result_info["semantic_slot"] = slot

                # Mark as promoted
                conn.execute(
                    """UPDATE learning_candidate
                       SET review_status = 'approved', suggested_action = 'upgrade_to_new_tag',
                           reviewed_by = ?, reviewed_at = ?
                       WHERE candidate_id = ?""",
                    (reviewed_by, now, cid),
                )

            elif action == "reject_noise":
                # Add to stopword and block
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO learning_stopword
                           (normalized_text, block_reason, blocked_by)
                           VALUES (?, 'auto_noise', ?)""",
                        (norm, reviewed_by),
                    )
                except Exception:
                    pass
                conn.execute(
                    """UPDATE learning_candidate
                       SET review_status = 'blocked', blocked_reason = 'auto_noise',
                           reviewed_by = ?, reviewed_at = ?
                       WHERE candidate_id = ?""",
                    (reviewed_by, now, cid),
                )
                result_info["blocked"] = True

            else:
                # become_rule_trigger or review → just mark approved for now
                conn.execute(
                    """UPDATE learning_candidate
                       SET review_status = 'approved',
                           reviewed_by = ?, reviewed_at = ?
                       WHERE candidate_id = ?""",
                    (reviewed_by, now, cid),
                )

            conn.commit()
            result_info["ok"] = True
            return result_info

    def batch_reject_noise(self, limit: int = 100) -> Dict:
        """Batch-reject all candidates classified as reject_noise.

        Adds them to learning_stopword and sets review_status='blocked'.
        Returns count of rejected candidates.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT candidate_id, normalized_text
                   FROM learning_candidate
                   WHERE suggested_action = 'reject_noise'
                     AND review_status = 'pending'
                   LIMIT ?""",
                (limit,),
            ).fetchall()

            if not rows:
                return {"rejected": 0}

            now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            rejected = 0
            for r in rows:
                cid, norm = r[0], r[1]
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO learning_stopword
                           (normalized_text, block_reason, blocked_by)
                           VALUES (?, 'auto_noise', 'system')""",
                        (norm,),
                    )
                    conn.execute(
                        """UPDATE learning_candidate
                           SET review_status = 'blocked', blocked_reason = 'auto_noise',
                               reviewed_by = 'system', reviewed_at = ?
                           WHERE candidate_id = ?""",
                        (now, cid),
                    )
                    rejected += 1
                except Exception:
                    pass

            conn.commit()
            return {"rejected": rejected}

    # ── Library Health & Tag Coverage ──

    def get_library_health(self) -> Dict:
        """Return comprehensive library health metrics.

        Provides:
        - Asset coverage: how many assets have tags, evidence, embeddings
        - Tag distribution: tags per semantic_slot with asset counts
        - Pipeline health: learning candidates, stopwords, feedback stats
        - Quality metrics: avg tag score, confidence band distribution
        - Weakest assets: assets with lowest tag coverage (candidates for re-analysis)
        """
        with self._connect() as conn:
            # ── 1. Asset counts ──
            total_assets = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]

            assets_with_tags = conn.execute(
                """SELECT COUNT(DISTINCT asset_id) FROM asset_tag_result
                   WHERE result_scope = 'asset' AND is_displayed = 1"""
            ).fetchone()[0]

            assets_with_evidence = conn.execute(
                "SELECT COUNT(DISTINCT asset_id) FROM evidence"
            ).fetchone()[0]

            assets_with_embedding = conn.execute(
                "SELECT COUNT(*) FROM assets WHERE uid IN (SELECT uid FROM asset_embeddings)"
            ).fetchone()[0] if self._table_exists(conn, "asset_embeddings") else 0

            assets_with_semantic = conn.execute(
                "SELECT COUNT(*) FROM assets WHERE semantic_json IS NOT NULL AND semantic_json != ''"
            ).fetchone()[0]

            # ── 2. Tag distribution by semantic_slot ──
            slot_dist = conn.execute(
                """SELECT t.semantic_slot,
                          COUNT(DISTINCT t.tag_id) AS tag_count,
                          COUNT(DISTINCT atr.asset_id) AS asset_count
                   FROM tag t
                   LEFT JOIN asset_tag_result atr ON atr.tag_id = t.tag_id
                       AND atr.result_scope = 'asset' AND atr.is_displayed = 1
                   WHERE t.is_active = 1
                   GROUP BY t.semantic_slot
                   ORDER BY asset_count DESC"""
            ).fetchall()

            tag_distribution = [
                {
                    "semantic_slot": r[0],
                    "tag_count": r[1],
                    "asset_count": r[2],
                    "coverage_pct": round(100.0 * r[2] / total_assets, 1) if total_assets > 0 else 0.0,
                }
                for r in slot_dist
            ]

            # ── 3. Top tags by usage ──
            top_tags = conn.execute(
                """SELECT t.tag_name, t.semantic_slot, COUNT(DISTINCT atr.asset_id) AS cnt
                   FROM tag t
                   JOIN asset_tag_result atr ON atr.tag_id = t.tag_id
                       AND atr.result_scope = 'asset' AND atr.is_displayed = 1
                   WHERE t.is_active = 1
                   GROUP BY t.tag_id
                   ORDER BY cnt DESC
                   LIMIT 20"""
            ).fetchall()

            top_tags_list = [
                {"tag_name": r[0], "semantic_slot": r[1], "asset_count": r[2]}
                for r in top_tags
            ]

            # ── 4. Quality metrics ──
            quality_row = conn.execute(
                """SELECT AVG(effective_score), AVG(final_score),
                          COUNT(CASE WHEN confidence_band = 'high' THEN 1 END),
                          COUNT(CASE WHEN confidence_band = 'medium' THEN 1 END),
                          COUNT(CASE WHEN confidence_band = 'low' THEN 1 END),
                          COUNT(*)
                   FROM asset_tag_result
                   WHERE result_scope = 'asset' AND is_displayed = 1"""
            ).fetchone()

            total_tag_results = quality_row[5] if quality_row else 0
            quality_metrics = {
                "avg_effective_score": round(quality_row[0], 3) if quality_row and quality_row[0] else 0.0,
                "avg_final_score": round(quality_row[1], 3) if quality_row and quality_row[1] else 0.0,
                "confidence_high": quality_row[2] if quality_row else 0,
                "confidence_medium": quality_row[3] if quality_row else 0,
                "confidence_low": quality_row[4] if quality_row else 0,
                "total_tag_results": total_tag_results,
                "avg_tags_per_asset": round(total_tag_results / assets_with_tags, 1) if assets_with_tags > 0 else 0.0,
            }

            # ── 5. User feedback stats ──
            feedback_counts = conn.execute(
                """SELECT feedback_type, COUNT(*)
                   FROM feedback_event
                   GROUP BY feedback_type"""
            ).fetchall()
            feedback_stats = {r[0]: r[1] for r in feedback_counts}

            user_confirmed = conn.execute(
                "SELECT COUNT(*) FROM asset_tag_result WHERE user_confirm_state = 'confirmed'"
            ).fetchone()[0]
            user_rejected = conn.execute(
                "SELECT COUNT(*) FROM asset_tag_result WHERE user_confirm_state = 'rejected'"
            ).fetchone()[0]

            # ── 6. Pipeline health ──
            candidate_counts = conn.execute(
                """SELECT review_status, COUNT(*)
                   FROM learning_candidate
                   GROUP BY review_status"""
            ).fetchall()
            candidate_stats = {r[0]: r[1] for r in candidate_counts}

            stopword_count = conn.execute(
                "SELECT COUNT(*) FROM learning_stopword"
            ).fetchone()[0]

            total_aliases = conn.execute(
                "SELECT COUNT(*) FROM tag_alias"
            ).fetchone()[0]
            learned_aliases = conn.execute(
                "SELECT COUNT(*) FROM tag_alias WHERE source_type = 'learned'"
            ).fetchone()[0]
            learned_tags = conn.execute(
                "SELECT COUNT(*) FROM tag WHERE source_type = 'learned'"
            ).fetchone()[0]

            custom_tags_active = conn.execute(
                "SELECT COUNT(*) FROM custom_tag WHERE status != 'archived'"
            ).fetchone()[0]

            composite_rules = conn.execute(
                "SELECT COUNT(*) FROM composite_rule WHERE is_active = 1"
            ).fetchone()[0]

            # ── 7. Weakest assets (lowest tag coverage) ──
            # Assets with fewest displayed tags (or no tags at all)
            weak_assets = conn.execute(
                """SELECT a.uid, a.filename,
                          COALESCE(tc.tag_count, 0) AS tag_count,
                          COALESCE(tc.avg_score, 0) AS avg_score
                   FROM assets a
                   LEFT JOIN (
                       SELECT asset_id,
                              COUNT(*) AS tag_count,
                              AVG(effective_score) AS avg_score
                       FROM asset_tag_result
                       WHERE result_scope = 'asset' AND is_displayed = 1
                       GROUP BY asset_id
                   ) tc ON tc.asset_id = a.uid
                   ORDER BY tag_count ASC, avg_score ASC
                   LIMIT 10"""
            ).fetchall()

            weakest_assets = [
                {
                    "uid": r[0],
                    "filename": r[1],
                    "tag_count": r[2],
                    "avg_score": round(r[3], 3) if r[3] else 0.0,
                }
                for r in weak_assets
            ]

            # ── 8. Evidence source distribution ──
            evidence_sources = conn.execute(
                """SELECT source_kind, COUNT(*) AS cnt
                   FROM evidence
                   GROUP BY source_kind
                   ORDER BY cnt DESC"""
            ).fetchall()
            evidence_by_source = {r[0]: r[1] for r in evidence_sources}

            return {
                "asset_coverage": {
                    "total_assets": total_assets,
                    "with_tags": assets_with_tags,
                    "with_evidence": assets_with_evidence,
                    "with_embedding": assets_with_embedding,
                    "with_semantic_json": assets_with_semantic,
                    "tag_coverage_pct": round(100.0 * assets_with_tags / total_assets, 1) if total_assets > 0 else 0.0,
                    "evidence_coverage_pct": round(100.0 * assets_with_evidence / total_assets, 1) if total_assets > 0 else 0.0,
                },
                "tag_distribution": tag_distribution,
                "top_tags": top_tags_list,
                "quality_metrics": quality_metrics,
                "feedback_stats": {
                    "by_type": feedback_stats,
                    "user_confirmed_tags": user_confirmed,
                    "user_rejected_tags": user_rejected,
                },
                "pipeline_health": {
                    "candidates": candidate_stats,
                    "stopword_count": stopword_count,
                    "total_aliases": total_aliases,
                    "learned_aliases": learned_aliases,
                    "learned_tags": learned_tags,
                    "custom_tags_active": custom_tags_active,
                    "composite_rules_active": composite_rules,
                },
                "weakest_assets": weakest_assets,
                "evidence_by_source": evidence_by_source,
            }

