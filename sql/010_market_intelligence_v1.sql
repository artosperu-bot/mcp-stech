SET NOCOUNT ON;
SET XACT_ABORT ON;

/* STECH MCP - Market Intelligence V1
   Additive/idempotent schema. No operational marketplace/ERP writes. */

IF OBJECT_ID(N'dbo.market_listing', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.market_listing (
        market_listing_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        source_code NVARCHAR(50) NOT NULL,
        seller_name NVARCHAR(200) NULL,
        external_listing_id NVARCHAR(200) NULL,
        external_sku NVARCHAR(200) NULL,
        title NVARCHAR(1000) NULL,
        url NVARCHAR(2000) NULL,
        currency CHAR(3) NOT NULL CONSTRAINT DF_market_listing_currency DEFAULT ('PEN'),
        is_stech BIT NOT NULL CONSTRAINT DF_market_listing_is_stech DEFAULT (0),
        first_seen_at DATETIME2(3) NOT NULL CONSTRAINT DF_market_listing_first_seen DEFAULT (SYSUTCDATETIME()),
        last_seen_at DATETIME2(3) NOT NULL CONSTRAINT DF_market_listing_last_seen DEFAULT (SYSUTCDATETIME()),
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_market_listing_created DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2(3) NOT NULL CONSTRAINT DF_market_listing_updated DEFAULT (SYSUTCDATETIME())
    );
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.market_listing') AND name = N'UX_market_listing_source_external')
    CREATE UNIQUE INDEX UX_market_listing_source_external
        ON dbo.market_listing(source_code, external_listing_id)
        WHERE external_listing_id IS NOT NULL;

IF OBJECT_ID(N'dbo.market_product_match', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.market_product_match (
        market_product_match_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        market_listing_id BIGINT NOT NULL,
        partnumber NVARCHAR(100) NOT NULL,
        match_status NVARCHAR(20) NOT NULL,
        match_method NVARCHAR(30) NOT NULL,
        confidence_score DECIMAL(5,2) NOT NULL,
        evidence_json NVARCHAR(MAX) NULL,
        verified_by NVARCHAR(100) NULL,
        verified_at DATETIME2(3) NULL,
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_market_product_match_created DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2(3) NOT NULL CONSTRAINT DF_market_product_match_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_market_product_match_listing FOREIGN KEY (market_listing_id) REFERENCES dbo.market_listing(market_listing_id),
        CONSTRAINT CK_market_product_match_status CHECK (match_status IN ('VERIFIED','PROBABLE','REVIEW','REJECTED')),
        CONSTRAINT CK_market_product_match_method CHECK (match_method IN ('PN_EXACT','EAN_EXACT','UPC_EXACT','MODEL_EXACT','MANUAL','OTHER')),
        CONSTRAINT CK_market_product_match_confidence CHECK (confidence_score >= 0 AND confidence_score <= 100),
        CONSTRAINT UQ_market_product_match_listing_part UNIQUE (market_listing_id, partnumber)
    );
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.market_product_match') AND name = N'IX_market_product_match_part_status')
    CREATE INDEX IX_market_product_match_part_status ON dbo.market_product_match(partnumber, match_status, confidence_score DESC);

IF OBJECT_ID(N'dbo.market_observation', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.market_observation (
        market_observation_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        market_listing_id BIGINT NOT NULL,
        observed_at DATETIME2(3) NOT NULL,
        price_regular DECIMAL(19,4) NULL,
        price_offer DECIMAL(19,4) NULL,
        price_effective DECIMAL(19,4) NULL,
        stock_qty DECIMAL(19,4) NULL,
        stock_state NVARCHAR(20) NOT NULL CONSTRAINT DF_market_observation_stock_state DEFAULT ('UNKNOWN'),
        promotion_text NVARCHAR(1000) NULL,
        promotion_type NVARCHAR(100) NULL,
        shipping_price DECIMAL(19,4) NULL,
        seller_count INT NULL,
        ranking_position INT NULL,
        source_method NVARCHAR(30) NOT NULL,
        source_observation_key NVARCHAR(300) NULL,
        raw_fingerprint CHAR(64) NULL,
        data_quality_score DECIMAL(5,2) NULL,
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_market_observation_created DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_market_observation_listing FOREIGN KEY (market_listing_id) REFERENCES dbo.market_listing(market_listing_id),
        CONSTRAINT CK_market_observation_stock_state CHECK (stock_state IN ('IN_STOCK','LOW_STOCK','OUT_OF_STOCK','UNKNOWN')),
        CONSTRAINT CK_market_observation_source_method CHECK (source_method IN ('API','COLLECTOR','WEB_RESEARCH','MANUAL','IMPORT')),
        CONSTRAINT CK_market_observation_quality CHECK (data_quality_score IS NULL OR (data_quality_score >= 0 AND data_quality_score <= 100))
    );
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.market_observation') AND name = N'IX_market_observation_listing_date')
    CREATE INDEX IX_market_observation_listing_date ON dbo.market_observation(market_listing_id, observed_at DESC);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.market_observation') AND name = N'UX_market_observation_source_key')
    CREATE UNIQUE INDEX UX_market_observation_source_key
        ON dbo.market_observation(market_listing_id, source_observation_key)
        WHERE source_observation_key IS NOT NULL;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.market_observation') AND name = N'UX_market_observation_fingerprint')
    CREATE UNIQUE INDEX UX_market_observation_fingerprint
        ON dbo.market_observation(market_listing_id, observed_at, raw_fingerprint)
        WHERE raw_fingerprint IS NOT NULL;

IF OBJECT_ID(N'dbo.supplier_observation', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.supplier_observation (
        supplier_observation_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        supplier_code NVARCHAR(50) NOT NULL,
        partnumber NVARCHAR(100) NOT NULL,
        observed_at DATETIME2(3) NOT NULL,
        cost_usd DECIMAL(19,6) NULL,
        cost_pen DECIMAL(19,6) NULL,
        stock_qty DECIMAL(19,4) NULL,
        stock_state NVARCHAR(20) NOT NULL CONSTRAINT DF_supplier_observation_stock_state DEFAULT ('UNKNOWN'),
        warehouse_code NVARCHAR(100) NULL,
        currency CHAR(3) NOT NULL,
        tax_included BIT NOT NULL CONSTRAINT DF_supplier_observation_tax DEFAULT (0),
        source_method NVARCHAR(30) NOT NULL,
        source_key NVARCHAR(300) NULL,
        data_quality_score DECIMAL(5,2) NULL,
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_supplier_observation_created DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT CK_supplier_observation_stock_state CHECK (stock_state IN ('IN_STOCK','LOW_STOCK','OUT_OF_STOCK','UNKNOWN')),
        CONSTRAINT CK_supplier_observation_quality CHECK (data_quality_score IS NULL OR (data_quality_score >= 0 AND data_quality_score <= 100))
    );
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.supplier_observation') AND name = N'IX_supplier_observation_part_date')
    CREATE INDEX IX_supplier_observation_part_date ON dbo.supplier_observation(partnumber, observed_at DESC, supplier_code);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.supplier_observation') AND name = N'UX_supplier_observation_source_key')
    CREATE UNIQUE INDEX UX_supplier_observation_source_key
        ON dbo.supplier_observation(supplier_code, source_key)
        WHERE source_key IS NOT NULL;

IF OBJECT_ID(N'dbo.market_pricing_policy', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.market_pricing_policy (
        policy_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        channel_code NVARCHAR(50) NOT NULL,
        category_code NVARCHAR(100) NULL,
        brand NVARCHAR(100) NULL,
        stech_margin_pct DECIMAL(9,6) NULL,
        minimum_margin_pct DECIMAL(9,6) NOT NULL,
        minimum_contribution_pen DECIMAL(19,4) NOT NULL CONSTRAINT DF_market_policy_min_contribution DEFAULT (0),
        undercut_amount_pen DECIMAL(19,4) NOT NULL CONSTRAINT DF_market_policy_undercut DEFAULT (1),
        strategy NVARCHAR(20) NOT NULL CONSTRAINT DF_market_policy_strategy DEFAULT ('BALANCED'),
        effective_from DATETIME2(3) NOT NULL,
        effective_to DATETIME2(3) NULL,
        is_active BIT NOT NULL CONSTRAINT DF_market_policy_active DEFAULT (1),
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_market_policy_created DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2(3) NOT NULL CONSTRAINT DF_market_policy_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT CK_market_policy_strategy CHECK (strategy IN ('BALANCED','MARGIN','VOLUME','CLEARANCE')),
        CONSTRAINT CK_market_policy_margin CHECK (minimum_margin_pct >= -1 AND minimum_margin_pct < 1),
        CONSTRAINT CK_market_policy_dates CHECK (effective_to IS NULL OR effective_to > effective_from)
    );
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.market_pricing_policy') AND name = N'IX_market_policy_lookup')
    CREATE INDEX IX_market_policy_lookup ON dbo.market_pricing_policy(channel_code, is_active, effective_from DESC, category_code, brand);

IF OBJECT_ID(N'dbo.market_channel_fee_rule', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.market_channel_fee_rule (
        fee_rule_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        channel_code NVARCHAR(50) NOT NULL,
        category_code NVARCHAR(100) NULL,
        commission_pct DECIMAL(9,6) NOT NULL CONSTRAINT DF_market_fee_commission DEFAULT (0),
        fixed_fee_pen DECIMAL(19,4) NOT NULL CONSTRAINT DF_market_fee_fixed DEFAULT (0),
        payment_fee_pct DECIMAL(9,6) NOT NULL CONSTRAINT DF_market_fee_payment DEFAULT (0),
        shipping_cost_pen DECIMAL(19,4) NULL,
        free_shipping_threshold_pen DECIMAL(19,4) NULL,
        seller_absorbs_shipping_above_threshold BIT NOT NULL CONSTRAINT DF_market_fee_absorbs DEFAULT (0),
        effective_from DATETIME2(3) NOT NULL,
        effective_to DATETIME2(3) NULL,
        is_active BIT NOT NULL CONSTRAINT DF_market_fee_active DEFAULT (1),
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_market_fee_created DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2(3) NOT NULL CONSTRAINT DF_market_fee_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT CK_market_fee_commission CHECK (commission_pct >= 0 AND commission_pct < 1),
        CONSTRAINT CK_market_fee_payment CHECK (payment_fee_pct >= 0 AND payment_fee_pct < 1),
        CONSTRAINT CK_market_fee_dates CHECK (effective_to IS NULL OR effective_to > effective_from)
    );
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.market_channel_fee_rule') AND name = N'IX_market_fee_lookup')
    CREATE INDEX IX_market_fee_lookup ON dbo.market_channel_fee_rule(channel_code, is_active, effective_from DESC, category_code);

IF OBJECT_ID(N'dbo.market_fx_rate', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.market_fx_rate (
        market_fx_rate_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        rate_date DATE NOT NULL,
        base_currency CHAR(3) NOT NULL,
        quote_currency CHAR(3) NOT NULL,
        rate DECIMAL(19,8) NOT NULL,
        source_code NVARCHAR(100) NOT NULL,
        observed_at DATETIME2(3) NOT NULL CONSTRAINT DF_market_fx_observed DEFAULT (SYSUTCDATETIME()),
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_market_fx_created DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT CK_market_fx_rate_positive CHECK (rate > 0),
        CONSTRAINT UQ_market_fx_rate UNIQUE (rate_date, base_currency, quote_currency, source_code)
    );
END;

IF OBJECT_ID(N'dbo.market_internal_signal', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.market_internal_signal (
        market_internal_signal_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        partnumber NVARCHAR(100) NOT NULL,
        observed_at DATETIME2(3) NOT NULL,
        own_stock_qty DECIMAL(19,4) NULL,
        sales_units_7d DECIMAL(19,4) NULL,
        sales_units_30d DECIMAL(19,4) NULL,
        sales_units_90d DECIMAL(19,4) NULL,
        days_since_last_sale INT NULL,
        inventory_age_days INT NULL,
        own_sale_price_pen DECIMAL(19,4) NULL,
        source_code NVARCHAR(100) NOT NULL,
        source_key NVARCHAR(300) NULL,
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_market_internal_signal_created DEFAULT (SYSUTCDATETIME())
    );
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.market_internal_signal') AND name = N'IX_market_internal_signal_part_date')
    CREATE INDEX IX_market_internal_signal_part_date ON dbo.market_internal_signal(partnumber, observed_at DESC);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.market_internal_signal') AND name = N'UX_market_internal_signal_source_key')
    CREATE UNIQUE INDEX UX_market_internal_signal_source_key
        ON dbo.market_internal_signal(source_code, source_key)
        WHERE source_key IS NOT NULL;

IF OBJECT_ID(N'dbo.market_recommendation_snapshot', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.market_recommendation_snapshot (
        market_recommendation_snapshot_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        partnumber NVARCHAR(100) NOT NULL,
        channel_code NVARCHAR(50) NULL,
        calculated_at DATETIME2(3) NOT NULL,
        action_code NVARCHAR(30) NOT NULL,
        opportunity_score DECIMAL(5,2) NULL,
        confidence_score DECIMAL(5,2) NOT NULL,
        risk_score DECIMAL(5,2) NOT NULL,
        recommended_price_pen DECIMAL(19,4) NULL,
        floor_price_pen DECIMAL(19,4) NULL,
        market_min_price_pen DECIMAL(19,4) NULL,
        market_median_price_pen DECIMAL(19,4) NULL,
        expected_profit_pen DECIMAL(19,4) NULL,
        expected_margin_pct DECIMAL(9,6) NULL,
        reason_codes_json NVARCHAR(MAX) NOT NULL,
        input_fingerprint CHAR(64) NOT NULL,
        created_at DATETIME2(3) NOT NULL CONSTRAINT DF_market_recommendation_created DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT CK_market_recommendation_action CHECK (action_code IN ('COMPRAR','PUBLICAR','SUBIR_STOCK','BAJAR_PRECIO','SUBIR_PRECIO','MANTENER','LIQUIDAR','NO_COMPETIR','REVISAR_PROVEEDOR','INVESTIGAR')),
        CONSTRAINT CK_market_recommendation_opportunity CHECK (opportunity_score IS NULL OR (opportunity_score >= 0 AND opportunity_score <= 100)),
        CONSTRAINT CK_market_recommendation_confidence CHECK (confidence_score >= 0 AND confidence_score <= 100),
        CONSTRAINT CK_market_recommendation_risk CHECK (risk_score >= 0 AND risk_score <= 100),
        CONSTRAINT UQ_market_recommendation_input UNIQUE (partnumber, channel_code, input_fingerprint)
    );
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.market_recommendation_snapshot') AND name = N'IX_market_recommendation_part_date')
    CREATE INDEX IX_market_recommendation_part_date ON dbo.market_recommendation_snapshot(partnumber, calculated_at DESC, channel_code);
