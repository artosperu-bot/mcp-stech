from __future__ import annotations

from typing import Any, Callable


_IMAGE_COLUMNS = (
    "imagen_id",
    "producto_distribuidor_id",
    "orden_imagen",
    "url_origen",
    "ruta_relativa",
    "ruta_actual",
    "nombre_archivo",
    "part_number_snapshot",
    "modelo_snapshot",
    "marca_snapshot",
    "ancho_px",
    "alto_px",
    "megapixeles",
    "tamano_bytes",
    "formato",
    "hash_sha256",
    "calidad",
    "estado_descarga",
    "estado_archivo",
    "ruta_papelera",
    "fecha_descarga",
    "fecha_verificacion",
    "fecha_eliminacion",
    "ultimo_error",
    "created_at",
    "updated_at",
    "categoria_snapshot",
    "subcategoria_snapshot",
)


class DeltronImageRepository:
    """Read-only access to dbo.PRD_DELTRON_IMAGEN in DB_DISTRIBUIDORES."""

    def __init__(self, connection_factory: Callable[[], Any]):
        self.connection_factory = connection_factory

    def list_for_product(self, producto_distribuidor_id: int) -> list[dict[str, Any]]:
        product_id = int(producto_distribuidor_id)
        column_sql = ",\n                    ".join(_IMAGE_COLUMNS)
        sql = f"""
                SELECT
                    {column_sql}
                FROM dbo.PRD_DELTRON_IMAGEN
                WHERE producto_distribuidor_id = ?
                ORDER BY orden_imagen ASC, imagen_id ASC
                """

        connection = self.connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(sql, product_id)
            columns = [item[0] for item in (cursor.description or [])]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            connection.close()
