-- ============================================================================
-- Tabla de respaldo en BI para toda la información descargada del portal
-- DETECNO (hoja "Facturas_Seleccionadas" del archivo final del flujo).
-- Servidor: 150.1.1.152 · Base de datos: BI
-- ============================================================================

USE [BI];
GO

IF OBJECT_ID('dbo.detecno_portal', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.detecno_portal (
        ID                                 INT             NOT NULL,
        SERIE                              NVARCHAR(10)    NOT NULL,
        FOLIO                              NVARCHAR(20)    NOT NULL,
        VERSION                            NVARCHAR(10)    NOT NULL,
        RFC_EMISOR                         NVARCHAR(20)    NOT NULL,
        NOMBRE_EMISOR                      NVARCHAR(200)   NOT NULL,
        RFC_RECEPTOR                       NVARCHAR(20)    NOT NULL,
        NOMBRE_RECEPTOR                    NVARCHAR(200)   NOT NULL,
        FECHA                              DATE            NULL,
        FECHA_RECEPCION                    DATE            NULL,
        TOTAL                              DECIMAL(18, 2)  NULL,
        USUARIO                            INT             NULL,
        METODOPAGO                         NVARCHAR(10)    NULL,
        UUID                               NVARCHAR(50)    NULL,
        MOTIVORECHAZO                      NVARCHAR(500)   NULL,
        ESTATUS                            NVARCHAR(50)    NULL,
        TIPOCOMPROBANTE                    NVARCHAR(5)     NULL,
        MONEDA                             NVARCHAR(5)     NULL,
        FECHATIMBRADO                      DATE            NULL,
        TOTALIMPUESTO_TRASLADADO           DECIMAL(18, 2)  NULL,
        TOTALIMPUESTO_RETENIDO             DECIMAL(18, 2)  NULL,
        estatusPagoEncId                   INT             NULL,
        estatusPagoEncDesc                 NVARCHAR(50)    NULL,
        peTotalAcumulado                   DECIMAL(18, 2)  NULL,
        peTotalCompensado                  DECIMAL(18, 2)  NULL,
        peTotalInsoluto                    DECIMAL(18, 2)  NULL,
        [ESTATUS SAT]                      NVARCHAR(50)    NULL,
        ESTATUSIDLN                        INT             NULL,
        ESTATUS_LISTAS_NEGRA               NVARCHAR(50)    NULL,
        FECHA_VALIDACION_LISTAS_NEGRAS     DATE            NULL,
        ESTATUSIDIMAGEN                    INT             NULL,
        NUM_ORDEN                          NVARCHAR(50)    NULL,
        CORREO_SANOFI                      NVARCHAR(200)   NULL,
        Pedimento                          NVARCHAR(50)    NULL,

        -- Columnas de auditoría del respaldo (no vienen del portal).
        FECHA_CARGA_BI                     DATETIME2(0)    NOT NULL CONSTRAINT DF_detecno_portal_FechaCarga DEFAULT (SYSDATETIME()),
        FECHA_ACTUALIZACION_BI             DATETIME2(0)    NULL,

        CONSTRAINT PK_detecno_portal PRIMARY KEY CLUSTERED (ID)
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_detecno_portal_UUID' AND object_id = OBJECT_ID('dbo.detecno_portal')
)
    CREATE NONCLUSTERED INDEX IX_detecno_portal_UUID ON dbo.detecno_portal (UUID);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_detecno_portal_Receptor_Fecha' AND object_id = OBJECT_ID('dbo.detecno_portal')
)
    CREATE NONCLUSTERED INDEX IX_detecno_portal_Receptor_Fecha
        ON dbo.detecno_portal (NOMBRE_RECEPTOR, FECHA);
GO
