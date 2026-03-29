-- 语义关键词系统参考表结构
-- 方言：偏 MySQL 8 写法，稍改即可迁移到 PostgreSQL
-- 版本：v1

CREATE TABLE tag_category (
    category_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    category_name VARCHAR(100) NOT NULL,
    category_code VARCHAR(100) NOT NULL UNIQUE,
    sort_order INT DEFAULT 0,
    is_active TINYINT DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE tag (
    tag_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    tag_name VARCHAR(150) NOT NULL,
    normalized_name VARCHAR(150) NOT NULL,
    tag_code VARCHAR(200) NOT NULL UNIQUE,
    category_id BIGINT NOT NULL,
    parent_tag_id BIGINT NULL,
    level_no INT DEFAULT 1,
    tag_type VARCHAR(50) NOT NULL,
    description TEXT NULL,
    trigger_objects JSON NULL,
    trigger_scenes JSON NULL,
    trigger_texts JSON NULL,
    negative_terms JSON NULL,
    score_threshold DECIMAL(5,4) DEFAULT 0.6000,
    confidence_prior DECIMAL(5,4) DEFAULT 0.5000,
    is_custom TINYINT DEFAULT 0,
    is_active TINYINT DEFAULT 1,
    review_status VARCHAR(30) DEFAULT 'approved',
    source_type VARCHAR(30) DEFAULT 'system',
    created_by VARCHAR(50) DEFAULT 'system',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_tag_category FOREIGN KEY (category_id) REFERENCES tag_category(category_id),
    CONSTRAINT fk_tag_parent FOREIGN KEY (parent_tag_id) REFERENCES tag(tag_id),
    UNIQUE KEY uk_tag_name_parent (normalized_name, parent_tag_id),
    KEY idx_tag_category (category_id),
    KEY idx_tag_type (tag_type),
    KEY idx_tag_parent (parent_tag_id),
    KEY idx_tag_active (is_active, review_status)
);

CREATE TABLE tag_alias (
    alias_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    tag_id BIGINT NOT NULL,
    alias_name VARCHAR(150) NOT NULL,
    alias_type VARCHAR(30) DEFAULT 'alias',
    language_code VARCHAR(10) DEFAULT 'zh-CN',
    weight_multiplier DECIMAL(5,4) DEFAULT 1.0000,
    source_type VARCHAR(30) DEFAULT 'system',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_alias_tag FOREIGN KEY (tag_id) REFERENCES tag(tag_id),
    UNIQUE KEY uk_tag_alias (tag_id, alias_name),
    KEY idx_alias_name (alias_name),
    KEY idx_alias_type (alias_type)
);

CREATE TABLE tag_relation (
    relation_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    from_tag_id BIGINT NOT NULL,
    to_tag_id BIGINT NOT NULL,
    relation_type VARCHAR(30) NOT NULL,
    relation_weight DECIMAL(5,4) DEFAULT 0.1000,
    note VARCHAR(255) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_relation_from FOREIGN KEY (from_tag_id) REFERENCES tag(tag_id),
    CONSTRAINT fk_relation_to FOREIGN KEY (to_tag_id) REFERENCES tag(tag_id),
    UNIQUE KEY uk_relation (from_tag_id, to_tag_id, relation_type),
    KEY idx_relation_from (from_tag_id, relation_type),
    KEY idx_relation_to (to_tag_id, relation_type)
);

CREATE TABLE composite_rule (
    rule_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    rule_name VARCHAR(200) NOT NULL,
    target_tag_id BIGINT NOT NULL,
    rule_type VARCHAR(30) DEFAULT 'cooccurrence',
    min_match_count INT DEFAULT 2,
    score_bonus DECIMAL(5,4) DEFAULT 0.1000,
    penalty_value DECIMAL(5,4) DEFAULT 0.0000,
    priority_no INT DEFAULT 100,
    is_active TINYINT DEFAULT 1,
    expr_json JSON NOT NULL,
    note TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_rule_target_tag FOREIGN KEY (target_tag_id) REFERENCES tag(tag_id),
    KEY idx_rule_target (target_tag_id, is_active),
    KEY idx_rule_priority (priority_no)
);

CREATE TABLE asset (
    asset_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NULL,
    asset_uuid CHAR(36) NOT NULL UNIQUE,
    asset_type VARCHAR(20) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_path TEXT NULL,
    file_hash VARCHAR(128) NULL,
    mime_type VARCHAR(100) NULL,
    duration_ms BIGINT DEFAULT 0,
    width_px INT NULL,
    height_px INT NULL,
    frame_rate DECIMAL(8,3) NULL,
    file_size_bytes BIGINT NULL,
    shot_time DATETIME NULL,
    timezone_name VARCHAR(64) NULL,
    gps_lat DECIMAL(10,7) NULL,
    gps_lng DECIMAL(10,7) NULL,
    exif_json JSON NULL,
    status VARCHAR(30) DEFAULT 'ready',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_asset_user (user_id),
    KEY idx_asset_type (asset_type),
    KEY idx_asset_hash (file_hash),
    KEY idx_asset_time (shot_time)
);

CREATE TABLE asset_segment (
    segment_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    asset_id BIGINT NOT NULL,
    segment_type VARCHAR(30) DEFAULT 'shot',
    segment_index_no INT DEFAULT 0,
    start_ms BIGINT DEFAULT 0,
    end_ms BIGINT DEFAULT 0,
    keyframe_path TEXT NULL,
    sample_frame_count INT DEFAULT 0,
    transcript_text TEXT NULL,
    ocr_text TEXT NULL,
    extra_json JSON NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_segment_asset FOREIGN KEY (asset_id) REFERENCES asset(asset_id),
    KEY idx_segment_asset (asset_id, segment_index_no),
    KEY idx_segment_time (asset_id, start_ms, end_ms)
);

CREATE TABLE evidence (
    evidence_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    asset_id BIGINT NOT NULL,
    segment_id BIGINT NULL,
    tag_id BIGINT NULL,
    source_kind VARCHAR(30) NOT NULL,
    source_model VARCHAR(100) NULL,
    source_version VARCHAR(50) NULL,
    raw_text VARCHAR(255) NULL,
    raw_value VARCHAR(255) NULL,
    bbox_json JSON NULL,
    span_start_ms BIGINT NULL,
    span_end_ms BIGINT NULL,
    base_score DECIMAL(5,4) NOT NULL,
    weighted_score DECIMAL(5,4) NOT NULL,
    evidence_json JSON NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_evidence_asset FOREIGN KEY (asset_id) REFERENCES asset(asset_id),
    CONSTRAINT fk_evidence_segment FOREIGN KEY (segment_id) REFERENCES asset_segment(segment_id),
    CONSTRAINT fk_evidence_tag FOREIGN KEY (tag_id) REFERENCES tag(tag_id),
    KEY idx_evidence_asset (asset_id),
    KEY idx_evidence_segment (segment_id),
    KEY idx_evidence_tag (tag_id),
    KEY idx_evidence_source (source_kind, source_model)
);

CREATE TABLE asset_tag_result (
    result_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    asset_id BIGINT NOT NULL,
    segment_id BIGINT NULL,
    tag_id BIGINT NOT NULL,
    result_scope VARCHAR(20) DEFAULT 'segment',
    base_score DECIMAL(5,4) DEFAULT 0.0000,
    source_bonus DECIMAL(5,4) DEFAULT 0.0000,
    cooccurrence_bonus DECIMAL(5,4) DEFAULT 0.0000,
    hierarchy_bonus DECIMAL(5,4) DEFAULT 0.0000,
    custom_boost DECIMAL(5,4) DEFAULT 0.0000,
    temporal_smooth DECIMAL(5,4) DEFAULT 0.0000,
    conflict_penalty DECIMAL(5,4) DEFAULT 0.0000,
    negative_penalty DECIMAL(5,4) DEFAULT 0.0000,
    final_score DECIMAL(5,4) NOT NULL,
    rank_no INT DEFAULT 0,
    is_displayed TINYINT DEFAULT 0,
    decision_reason JSON NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_result_asset FOREIGN KEY (asset_id) REFERENCES asset(asset_id),
    CONSTRAINT fk_result_segment FOREIGN KEY (segment_id) REFERENCES asset_segment(segment_id),
    CONSTRAINT fk_result_tag FOREIGN KEY (tag_id) REFERENCES tag(tag_id),
    UNIQUE KEY uk_asset_segment_tag (asset_id, segment_id, tag_id, result_scope),
    KEY idx_result_asset_score (asset_id, final_score),
    KEY idx_result_tag_score (tag_id, final_score),
    KEY idx_result_segment_score (segment_id, final_score),
    KEY idx_result_displayed (is_displayed, final_score)
);

CREATE TABLE custom_tag (
    custom_tag_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    workspace_id BIGINT NULL,
    custom_tag_name VARCHAR(150) NOT NULL,
    normalized_name VARCHAR(150) NOT NULL,
    parent_system_tag_id BIGINT NULL,
    category_id BIGINT NULL,
    aliases JSON NULL,
    related_objects JSON NULL,
    related_scenes JSON NULL,
    trigger_texts JSON NULL,
    negative_terms JSON NULL,
    threshold_value DECIMAL(5,4) DEFAULT 0.7200,
    auto_expand TINYINT DEFAULT 1,
    review_mode VARCHAR(30) DEFAULT 'manual',
    status VARCHAR(30) DEFAULT 'gray',
    note TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_custom_parent_tag FOREIGN KEY (parent_system_tag_id) REFERENCES tag(tag_id),
    CONSTRAINT fk_custom_category FOREIGN KEY (category_id) REFERENCES tag_category(category_id),
    UNIQUE KEY uk_user_custom_tag (user_id, normalized_name),
    KEY idx_custom_user (user_id, workspace_id),
    KEY idx_custom_status (status)
);

CREATE TABLE custom_tag_mapping (
    mapping_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    custom_tag_id BIGINT NOT NULL,
    system_tag_id BIGINT NOT NULL,
    mapping_type VARCHAR(30) DEFAULT 'parent',
    mapping_weight DECIMAL(5,4) DEFAULT 0.5000,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_mapping_custom FOREIGN KEY (custom_tag_id) REFERENCES custom_tag(custom_tag_id),
    CONSTRAINT fk_mapping_system FOREIGN KEY (system_tag_id) REFERENCES tag(tag_id),
    UNIQUE KEY uk_custom_mapping (custom_tag_id, system_tag_id, mapping_type)
);

CREATE TABLE learning_candidate (
    candidate_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    candidate_text VARCHAR(200) NOT NULL,
    normalized_text VARCHAR(200) NOT NULL,
    category_hint VARCHAR(50) NULL,
    source_kind VARCHAR(30) NOT NULL,
    first_seen_at DATETIME NULL,
    last_seen_at DATETIME NULL,
    occurrence_count INT DEFAULT 1,
    asset_count INT DEFAULT 1,
    confirmed_count INT DEFAULT 0,
    rejected_count INT DEFAULT 0,
    cooccur_json JSON NULL,
    suggested_tag_id BIGINT NULL,
    suggested_action VARCHAR(30) DEFAULT 'review',
    confidence_score DECIMAL(5,4) DEFAULT 0.0000,
    review_status VARCHAR(30) DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_candidate_suggested_tag FOREIGN KEY (suggested_tag_id) REFERENCES tag(tag_id),
    UNIQUE KEY uk_candidate_text_source (normalized_text, source_kind),
    KEY idx_candidate_status (review_status, confidence_score),
    KEY idx_candidate_occurrence (occurrence_count, asset_count)
);

CREATE TABLE feedback_event (
    feedback_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    asset_id BIGINT NOT NULL,
    segment_id BIGINT NULL,
    tag_id BIGINT NULL,
    custom_tag_id BIGINT NULL,
    feedback_type VARCHAR(30) NOT NULL,
    feedback_value VARCHAR(100) NULL,
    note TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_feedback_asset FOREIGN KEY (asset_id) REFERENCES asset(asset_id),
    CONSTRAINT fk_feedback_segment FOREIGN KEY (segment_id) REFERENCES asset_segment(segment_id),
    CONSTRAINT fk_feedback_tag FOREIGN KEY (tag_id) REFERENCES tag(tag_id),
    CONSTRAINT fk_feedback_custom_tag FOREIGN KEY (custom_tag_id) REFERENCES custom_tag(custom_tag_id),
    KEY idx_feedback_user (user_id, created_at),
    KEY idx_feedback_asset (asset_id),
    KEY idx_feedback_tag (tag_id, feedback_type)
);

CREATE TABLE tag_version_log (
    version_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    version_name VARCHAR(30) NOT NULL UNIQUE,
    change_type VARCHAR(30) NOT NULL,
    change_summary TEXT NULL,
    change_payload JSON NULL,
    created_by VARCHAR(50) DEFAULT 'system',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 推荐初始化关系类型：
-- parent / child / synonym / alias / related / conflict / cooccurs / near / prerequisite

-- 推荐初始化 evidence.source_kind：
-- vision_object / vision_scene / vision_action / ocr / asr / metadata / exif / gps / rule / user_feedback

-- 推荐初始化 asset_tag_result.result_scope：
-- asset / segment / frame