-- Generated from backend/app/models.py. Do not edit by hand.

CREATE TABLE rating_scale (
	id INTEGER NOT NULL, 
	code VARCHAR(40) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	min_value INTEGER NOT NULL, 
	max_value INTEGER NOT NULL, 
	description TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_scale_range CHECK (max_value > min_value), 
	UNIQUE (code)
);

CREATE TABLE subject_type (
	id INTEGER NOT NULL, 
	code VARCHAR(40) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	description TEXT, 
	PRIMARY KEY (id), 
	UNIQUE (code)
);

CREATE TABLE audit_event (
	id INTEGER NOT NULL, 
	entity VARCHAR(30) NOT NULL, 
	entity_id INTEGER NOT NULL, 
	action VARCHAR(30) NOT NULL, 
	from_state VARCHAR(20), 
	to_state VARCHAR(20), 
	actor VARCHAR(120) NOT NULL, 
	details JSON NOT NULL, 
	at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_audit_event_entity_id ON audit_event (entity_id);

CREATE INDEX ix_audit_event_at ON audit_event (at);

CREATE TABLE rating_band (
	id INTEGER NOT NULL, 
	scale_id INTEGER NOT NULL, 
	label VARCHAR(40) NOT NULL, 
	lower_bound FLOAT NOT NULL, 
	color_hex VARCHAR(7) NOT NULL, 
	font_hex VARCHAR(7) NOT NULL, 
	rag VARCHAR(5) NOT NULL, 
	meaning TEXT, 
	PRIMARY KEY (id), 
	UNIQUE (scale_id, lower_bound), 
	FOREIGN KEY(scale_id) REFERENCES rating_scale (id) ON DELETE CASCADE
);

CREATE TABLE scorecard (
	id INTEGER NOT NULL, 
	code VARCHAR(60) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	subject_type_id INTEGER NOT NULL, 
	owner VARCHAR(120), 
	tags JSON NOT NULL, 
	is_template BOOLEAN NOT NULL, 
	requires_review BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	archived_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (code), 
	FOREIGN KEY(subject_type_id) REFERENCES subject_type (id)
);

CREATE TABLE subject (
	id INTEGER NOT NULL, 
	code VARCHAR(60) NOT NULL, 
	name VARCHAR(300) NOT NULL, 
	subject_type_id INTEGER NOT NULL, 
	parent_id INTEGER, 
	owner VARCHAR(120) NOT NULL, 
	description TEXT, 
	due_at DATETIME, 
	budget FLOAT, 
	created_at DATETIME NOT NULL, 
	archived_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (code), 
	FOREIGN KEY(subject_type_id) REFERENCES subject_type (id), 
	FOREIGN KEY(parent_id) REFERENCES subject (id)
);

CREATE TABLE scorecard_version (
	id INTEGER NOT NULL, 
	scorecard_id INTEGER NOT NULL, 
	version_no INTEGER NOT NULL, 
	status VARCHAR(12) NOT NULL, 
	purpose TEXT NOT NULL, 
	scope TEXT NOT NULL, 
	objective TEXT NOT NULL, 
	guidance TEXT, 
	rating_scale_id INTEGER NOT NULL, 
	target_score FLOAT NOT NULL, 
	aggregation VARCHAR(20) NOT NULL, 
	max_depth INTEGER NOT NULL, 
	qtc_enabled BOOLEAN NOT NULL, 
	required_judges INTEGER NOT NULL, 
	judge_tolerance_pct FLOAT NOT NULL, 
	require_self_appraisal BOOLEAN NOT NULL, 
	is_foundational BOOLEAN NOT NULL, 
	based_on_version_id INTEGER, 
	change_note TEXT, 
	created_at DATETIME NOT NULL, 
	published_at DATETIME, 
	retired_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (scorecard_id, version_no), 
	CONSTRAINT ck_version_status CHECK (status in ('draft','in_review','published','retired')), 
	CONSTRAINT ck_version_judges CHECK (required_judges between 1 and 5), 
	CONSTRAINT ck_version_agg CHECK (aggregation in ('weighted_mean','minimum')), 
	CONSTRAINT ck_version_depth CHECK (max_depth between 1 and 6), 
	FOREIGN KEY(scorecard_id) REFERENCES scorecard (id) ON DELETE CASCADE, 
	FOREIGN KEY(rating_scale_id) REFERENCES rating_scale (id), 
	FOREIGN KEY(based_on_version_id) REFERENCES scorecard_version (id)
);

CREATE TABLE parameter (
	id INTEGER NOT NULL, 
	version_id INTEGER NOT NULL, 
	parent_id INTEGER, 
	code VARCHAR(40) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	description TEXT, 
	weight FLOAT NOT NULL, 
	sort_order INTEGER NOT NULL, 
	aggregation VARCHAR(20) NOT NULL, 
	is_critical BOOLEAN NOT NULL, 
	min_acceptable_score FLOAT, 
	is_optional BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (version_id, code), 
	CONSTRAINT ck_param_weight CHECK (weight >= 0), 
	CONSTRAINT ck_param_agg CHECK (aggregation in ('weighted_mean','minimum')), 
	FOREIGN KEY(version_id) REFERENCES scorecard_version (id) ON DELETE CASCADE, 
	FOREIGN KEY(parent_id) REFERENCES parameter (id) ON DELETE CASCADE
);

CREATE TABLE version_review (
	id INTEGER NOT NULL, 
	version_id INTEGER NOT NULL, 
	action VARCHAR(20) NOT NULL, 
	actor VARCHAR(120) NOT NULL, 
	comment TEXT, 
	at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(version_id) REFERENCES scorecard_version (id) ON DELETE CASCADE
);

CREATE TABLE submission (
	id INTEGER NOT NULL, 
	subject_id INTEGER NOT NULL, 
	version_id INTEGER NOT NULL, 
	attempt_no INTEGER NOT NULL, 
	previous_id INTEGER, 
	owner VARCHAR(120) NOT NULL, 
	status VARCHAR(15) NOT NULL, 
	title VARCHAR(300), 
	input_text TEXT, 
	actual_cost FLOAT, 
	created_at DATETIME NOT NULL, 
	submitted_at DATETIME, 
	decided_at DATETIME, 
	decision VARCHAR(10), 
	official_score FLOAT, 
	official_band VARCHAR(40), 
	official_rag VARCHAR(5), 
	judge_spread_pct FLOAT, 
	gate_failures JSON NOT NULL, 
	time_met BOOLEAN, 
	cost_met BOOLEAN, 
	qtc_green BOOLEAN, 
	adjudicated BOOLEAN NOT NULL, 
	decided_by VARCHAR(120), 
	decision_reason TEXT, 
	blocks_project BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_sub_status CHECK (status in ('open','in_review','adjudication','decided','withdrawn','cancelled')), 
	CONSTRAINT ck_sub_decision CHECK (decision is null or decision in ('passed','redo')), 
	UNIQUE (subject_id, version_id, attempt_no), 
	FOREIGN KEY(subject_id) REFERENCES subject (id), 
	FOREIGN KEY(version_id) REFERENCES scorecard_version (id), 
	FOREIGN KEY(previous_id) REFERENCES submission (id)
);

CREATE TABLE rating_criterion (
	id INTEGER NOT NULL, 
	parameter_id INTEGER NOT NULL, 
	score_min INTEGER NOT NULL, 
	score_max INTEGER NOT NULL, 
	qualitative TEXT NOT NULL, 
	quantitative TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_criterion_range CHECK (score_max >= score_min), 
	FOREIGN KEY(parameter_id) REFERENCES parameter (id) ON DELETE CASCADE
);

CREATE TABLE metric (
	id INTEGER NOT NULL, 
	parameter_id INTEGER NOT NULL, 
	code VARCHAR(60) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	unit VARCHAR(40), 
	data_type VARCHAR(10) NOT NULL, 
	description TEXT, 
	sort_order INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (parameter_id, code), 
	CONSTRAINT ck_metric_type CHECK (data_type in ('number','percent','count','boolean')), 
	FOREIGN KEY(parameter_id) REFERENCES parameter (id) ON DELETE CASCADE
);

CREATE TABLE evaluation (
	id INTEGER NOT NULL, 
	version_id INTEGER NOT NULL, 
	subject_name VARCHAR(300) NOT NULL, 
	subject_ref VARCHAR(120), 
	input_text TEXT, 
	evaluator_type VARCHAR(10) NOT NULL, 
	evaluator_name VARCHAR(120), 
	judge_model VARCHAR(80), 
	is_private BOOLEAN NOT NULL, 
	status VARCHAR(12) NOT NULL, 
	target_score FLOAT NOT NULL, 
	time_met BOOLEAN, 
	cost_met BOOLEAN, 
	attempt_no INTEGER NOT NULL, 
	origin VARCHAR(10) NOT NULL, 
	origin_ref VARCHAR(300), 
	final_score FLOAT, 
	band_label VARCHAR(40), 
	rag VARCHAR(5), 
	quality_met BOOLEAN, 
	qtc_green BOOLEAN, 
	gate_failures JSON NOT NULL, 
	summary TEXT, 
	notes TEXT, 
	created_at DATETIME NOT NULL, 
	completed_at DATETIME, 
	voided_reason TEXT, 
	subject_id INTEGER, 
	submission_id INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_eval_status CHECK (status in ('draft','completed','void')), 
	CONSTRAINT ck_eval_type CHECK (evaluator_type in ('self','human','llm')), 
	CONSTRAINT ck_eval_origin CHECK (origin in ('app','import')), 
	FOREIGN KEY(version_id) REFERENCES scorecard_version (id), 
	FOREIGN KEY(subject_id) REFERENCES subject (id), 
	FOREIGN KEY(submission_id) REFERENCES submission (id)
);

CREATE TABLE diagnosis (
	id INTEGER NOT NULL, 
	person VARCHAR(120) NOT NULL, 
	cause VARCHAR(12) NOT NULL, 
	action VARCHAR(12) NOT NULL, 
	notes TEXT, 
	submission_id INTEGER, 
	recorded_by VARCHAR(120) NOT NULL, 
	recorded_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_diag_cause CHECK (cause in ('skill','aptitude','will','allocation')), 
	CONSTRAINT ck_diag_action CHECK (action in ('train','reassign','discuss','rescope','none')), 
	FOREIGN KEY(submission_id) REFERENCES submission (id)
);

CREATE TABLE metric_threshold (
	id INTEGER NOT NULL, 
	metric_id INTEGER NOT NULL, 
	min_value FLOAT, 
	max_value FLOAT, 
	score FLOAT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(metric_id) REFERENCES metric (id) ON DELETE CASCADE
);

CREATE TABLE evaluation_document (
	id INTEGER NOT NULL, 
	evaluation_id INTEGER NOT NULL, 
	filename VARCHAR(255) NOT NULL, 
	media_type VARCHAR(100), 
	content_text TEXT NOT NULL, 
	uploaded_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(evaluation_id) REFERENCES evaluation (id) ON DELETE CASCADE
);

CREATE TABLE metric_value (
	id INTEGER NOT NULL, 
	evaluation_id INTEGER NOT NULL, 
	metric_id INTEGER NOT NULL, 
	value FLOAT NOT NULL, 
	source VARCHAR(20) NOT NULL, 
	note TEXT, 
	PRIMARY KEY (id), 
	UNIQUE (evaluation_id, metric_id), 
	FOREIGN KEY(evaluation_id) REFERENCES evaluation (id) ON DELETE CASCADE, 
	FOREIGN KEY(metric_id) REFERENCES metric (id)
);

CREATE TABLE parameter_result (
	id INTEGER NOT NULL, 
	evaluation_id INTEGER NOT NULL, 
	parameter_id INTEGER NOT NULL, 
	is_leaf BOOLEAN NOT NULL, 
	judged_score FLOAT, 
	computed_score FLOAT, 
	final_score FLOAT, 
	score_source VARCHAR(20) NOT NULL, 
	not_applicable BOOLEAN NOT NULL, 
	rationale TEXT, 
	evidence TEXT, 
	confidence FLOAT, 
	override_reason TEXT, 
	effective_weight FLOAT, 
	band_label VARCHAR(40), 
	PRIMARY KEY (id), 
	UNIQUE (evaluation_id, parameter_id), 
	CONSTRAINT ck_result_source CHECK (score_source in ('judged','metric','override','rollup','not_applicable','pending')), 
	FOREIGN KEY(evaluation_id) REFERENCES evaluation (id) ON DELETE CASCADE, 
	FOREIGN KEY(parameter_id) REFERENCES parameter (id)
);

