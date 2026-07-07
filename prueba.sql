IF OBJECT_ID('tempdb..#Folios') IS NULL
BEGIN
    CREATE TABLE #Folios (
        [FOLIO_ ABC] NVARCHAR(100) COLLATE DATABASE_DEFAULT NOT NULL PRIMARY KEY
    );
END;

SELECT
    folios.[FOLIO_ ABC],
    MAX(base.[Pedimento]) AS [Pedimento]
FROM #Folios AS folios
LEFT JOIN (
    SELECT
        ISNULL(
            CONCAT(
                SUBSTRING(TRIM([CuentaG_Folio_Num_Factura]), 1, 1),
                TRIM([CuentaG_FolioFactura])
            ),
            '-'
        ) AS [FOLIO_ ABC],
        [Pedimento]
    FROM [Admin].SIR_VT_Sabana_Pedimento_ABC
) AS base
    ON base.[FOLIO_ ABC] COLLATE DATABASE_DEFAULT = folios.[FOLIO_ ABC] COLLATE DATABASE_DEFAULT
GROUP BY folios.[FOLIO_ ABC];
