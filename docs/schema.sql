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
	created_at DATETIME NOT NULL, 
	archived_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (code), 
	FOREIGN KEY(subject_type_id) REFERENCES subject_type (id)
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
	based_on_version_id INTEGER, 
	change_note TEXT, 
	created_at DATETIME NOT NULL, 
	published_at DATETIME, 
	retired_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (scorecard_id, version_no), 
	CONSTRAINT ck_version_status CHECK (status in ('draft','published','retired')), 
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
	PRIMARY KEY (id), 
	CONSTRAINT ck_eval_status CHECK (status in ('draft','completed','void')), 
	CONSTRAINT ck_eval_type CHECK (evaluator_type in ('self','human','llm')), 
	CONSTRAINT ck_eval_origin CHECK (origin in ('app','import')), 
	FOREIGN KEY(version_id) REFERENCES scorecard_version (id)
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

CREATE TABLE metric_threshold (
	id INTEGER NOT NULL, 
	metric_id INTEGER NOT NULL, 
	min_value FLOAT, 
	max_value FLOAT, 
	score FLOAT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(metric_id) REFERENCES metric (id) ON DELETE CASCADE
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

