USE [STECH_MCP];
GO

IF OBJECT_ID(N'dbo.product_attribute_definition', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_attribute_definition (
        field_code NVARCHAR(100) NOT NULL CONSTRAINT PK_product_attribute_definition PRIMARY KEY,
        display_name NVARCHAR(200) NOT NULL,
        value_type VARCHAR(30) NOT NULL,
        unit NVARCHAR(40) NULL,
        variant_sensitive BIT NOT NULL CONSTRAINT DF_product_attribute_definition_variant DEFAULT (0),
        reuse_policy VARCHAR(40) NOT NULL,
        enabled BIT NOT NULL CONSTRAINT DF_product_attribute_definition_enabled DEFAULT (1),
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_attribute_definition_created DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_product_attribute_definition_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT CK_product_attribute_definition_value_type CHECK (
            value_type IN ('TEXT', 'NUMBER', 'BOOLEAN', 'DIMENSIONS', 'RANGE', 'LIST')
        ),
        CONSTRAINT CK_product_attribute_definition_reuse_policy CHECK (
            reuse_policy IN ('EXACT_PN_ONLY', 'SAME_CHASSIS_ALLOWED')
        )
    );
END;
GO

IF OBJECT_ID(N'dbo.category_attribute', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.category_attribute (
        category_code NVARCHAR(80) NOT NULL,
        field_code NVARCHAR(100) NOT NULL,
        requirement VARCHAR(20) NOT NULL,
        ordinal INT NOT NULL,
        active BIT NOT NULL CONSTRAINT DF_category_attribute_active DEFAULT (1),
        created_at DATETIME2(0) NOT NULL CONSTRAINT DF_category_attribute_created DEFAULT (SYSUTCDATETIME()),
        updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_category_attribute_updated DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT PK_category_attribute PRIMARY KEY (category_code, field_code),
        CONSTRAINT FK_category_attribute_definition FOREIGN KEY (field_code)
            REFERENCES dbo.product_attribute_definition(field_code),
        CONSTRAINT CK_category_attribute_requirement CHECK (
            requirement IN ('REQUIRED', 'RECOMMENDED')
        ),
        CONSTRAINT CK_category_attribute_ordinal CHECK (ordinal > 0)
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.category_attribute')
      AND name = N'IX_category_attribute_category_ordinal'
)
BEGIN
    CREATE INDEX IX_category_attribute_category_ordinal
        ON dbo.category_attribute(category_code, active, ordinal, field_code);
END;
GO

MERGE dbo.product_attribute_definition AS target
USING (VALUES
    (N'cpu_model',                 N'Modelo de procesador',           'TEXT',       NULL,   1, 'EXACT_PN_ONLY'),
    (N'ram_gb',                    N'Memoria RAM',                    'NUMBER',     N'GB',  1, 'EXACT_PN_ONLY'),
    (N'storage_gb',                N'Capacidad de almacenamiento',    'NUMBER',     N'GB',  1, 'EXACT_PN_ONLY'),
    (N'storage_type',              N'Tipo de almacenamiento',         'TEXT',       NULL,   1, 'EXACT_PN_ONLY'),
    (N'screen_inches',             N'Tamaño de pantalla',             'NUMBER',     N'in',  0, 'EXACT_PN_ONLY'),
    (N'resolution',                N'Resolución',                     'TEXT',       NULL,   0, 'EXACT_PN_ONLY'),
    (N'wifi',                      N'Wi-Fi',                          'TEXT',       NULL,   0, 'EXACT_PN_ONLY'),
    (N'bluetooth_version',         N'Versión Bluetooth',              'TEXT',       NULL,   0, 'EXACT_PN_ONLY'),
    (N'battery_wh',                N'Capacidad de batería',            'NUMBER',     N'Wh',  1, 'EXACT_PN_ONLY'),
    (N'weight_kg',                 N'Peso',                           'NUMBER',     N'kg',  0, 'SAME_CHASSIS_ALLOWED'),
    (N'dimensions_mm',             N'Dimensiones',                    'DIMENSIONS', N'mm',  0, 'SAME_CHASSIS_ALLOWED'),
    (N'os_name',                   N'Sistema operativo',              'TEXT',       NULL,   1, 'EXACT_PN_ONLY'),

    (N'speaker_power_w',           N'Potencia del parlante',          'NUMBER',     N'W',   1, 'EXACT_PN_ONLY'),
    (N'battery_runtime_hours',     N'Autonomía de batería',           'NUMBER',     N'h',   1, 'EXACT_PN_ONLY'),
    (N'battery_capacity_wh',       N'Capacidad de batería',            'NUMBER',     N'Wh',  1, 'EXACT_PN_ONLY'),
    (N'ip_rating',                 N'Protección IP',                   'TEXT',       NULL,   0, 'EXACT_PN_ONLY'),
    (N'frequency_response_hz',     N'Respuesta de frecuencia',        'RANGE',      N'Hz',  0, 'EXACT_PN_ONLY'),
    (N'box_contents',              N'Contenido de caja',               'LIST',       NULL,   0, 'EXACT_PN_ONLY'),

    (N'driver_size_mm',            N'Tamaño del driver',              'NUMBER',     N'mm',  0, 'EXACT_PN_ONLY'),
    (N'anc',                       N'Cancelación activa de ruido',     'BOOLEAN',    NULL,   0, 'EXACT_PN_ONLY'),
    (N'transparency_mode',         N'Modo transparencia',              'BOOLEAN',    NULL,   0, 'EXACT_PN_ONLY'),
    (N'codec',                     N'Códecs de audio',                 'LIST',       NULL,   0, 'EXACT_PN_ONLY'),
    (N'microphone',                N'Micrófono',                       'BOOLEAN',    NULL,   0, 'EXACT_PN_ONLY'),
    (N'charging_time_hours',       N'Tiempo de carga',                 'NUMBER',     N'h',   1, 'EXACT_PN_ONLY'),
    (N'impedance_ohm',             N'Impedancia',                      'NUMBER',     N'ohm', 0, 'EXACT_PN_ONLY'),
    (N'sensitivity_db',            N'Sensibilidad',                    'NUMBER',     N'dB',  0, 'EXACT_PN_ONLY'),
    (N'weight_g',                  N'Peso',                            'NUMBER',     N'g',   0, 'SAME_CHASSIS_ALLOWED')
) AS source(field_code, display_name, value_type, unit, variant_sensitive, reuse_policy)
ON target.field_code = source.field_code
WHEN MATCHED THEN
    UPDATE SET
        display_name = source.display_name,
        value_type = source.value_type,
        unit = source.unit,
        variant_sensitive = source.variant_sensitive,
        reuse_policy = source.reuse_policy,
        enabled = 1,
        updated_at = SYSUTCDATETIME()
WHEN NOT MATCHED THEN
    INSERT (field_code, display_name, value_type, unit, variant_sensitive, reuse_policy, enabled)
    VALUES (source.field_code, source.display_name, source.value_type, source.unit, source.variant_sensitive, source.reuse_policy, 1);
GO

MERGE dbo.category_attribute AS target
USING (VALUES
    (N'LAPTOP', N'cpu_model',             'REQUIRED',    10),
    (N'LAPTOP', N'ram_gb',                'REQUIRED',    20),
    (N'LAPTOP', N'storage_gb',            'REQUIRED',    30),
    (N'LAPTOP', N'storage_type',          'REQUIRED',    40),
    (N'LAPTOP', N'screen_inches',         'REQUIRED',    50),
    (N'LAPTOP', N'resolution',            'REQUIRED',    60),
    (N'LAPTOP', N'wifi',                  'RECOMMENDED', 70),
    (N'LAPTOP', N'bluetooth_version',     'RECOMMENDED', 80),
    (N'LAPTOP', N'battery_wh',            'RECOMMENDED', 90),
    (N'LAPTOP', N'weight_kg',             'RECOMMENDED', 100),
    (N'LAPTOP', N'dimensions_mm',         'RECOMMENDED', 110),
    (N'LAPTOP', N'os_name',               'REQUIRED',    120),

    (N'PORTABLE_SPEAKER', N'speaker_power_w',       'REQUIRED',    10),
    (N'PORTABLE_SPEAKER', N'bluetooth_version',     'REQUIRED',    20),
    (N'PORTABLE_SPEAKER', N'battery_runtime_hours', 'REQUIRED',    30),
    (N'PORTABLE_SPEAKER', N'battery_capacity_wh',   'RECOMMENDED', 40),
    (N'PORTABLE_SPEAKER', N'ip_rating',             'REQUIRED',    50),
    (N'PORTABLE_SPEAKER', N'frequency_response_hz', 'RECOMMENDED', 60),
    (N'PORTABLE_SPEAKER', N'weight_kg',             'RECOMMENDED', 70),
    (N'PORTABLE_SPEAKER', N'dimensions_mm',         'RECOMMENDED', 80),
    (N'PORTABLE_SPEAKER', N'box_contents',          'RECOMMENDED', 90),

    (N'HEADPHONES', N'driver_size_mm',        'REQUIRED',    10),
    (N'HEADPHONES', N'anc',                   'RECOMMENDED', 20),
    (N'HEADPHONES', N'transparency_mode',     'RECOMMENDED', 30),
    (N'HEADPHONES', N'bluetooth_version',     'REQUIRED',    40),
    (N'HEADPHONES', N'codec',                 'RECOMMENDED', 50),
    (N'HEADPHONES', N'microphone',            'REQUIRED',    60),
    (N'HEADPHONES', N'battery_runtime_hours', 'REQUIRED',    70),
    (N'HEADPHONES', N'charging_time_hours',   'RECOMMENDED', 80),
    (N'HEADPHONES', N'impedance_ohm',         'RECOMMENDED', 90),
    (N'HEADPHONES', N'sensitivity_db',        'RECOMMENDED', 100),
    (N'HEADPHONES', N'frequency_response_hz', 'RECOMMENDED', 110),
    (N'HEADPHONES', N'weight_g',              'RECOMMENDED', 120)
) AS source(category_code, field_code, requirement, ordinal)
ON target.category_code = source.category_code
AND target.field_code = source.field_code
WHEN MATCHED THEN
    UPDATE SET
        requirement = source.requirement,
        ordinal = source.ordinal,
        active = 1,
        updated_at = SYSUTCDATETIME()
WHEN NOT MATCHED THEN
    INSERT (category_code, field_code, requirement, ordinal, active)
    VALUES (source.category_code, source.field_code, source.requirement, source.ordinal, 1);
GO
