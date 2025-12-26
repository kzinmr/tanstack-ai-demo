import { useEffect, useMemo, useRef, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { ArtifactData } from "../types";
import { fetchArtifactData } from "../services/dataService";

type ArtifactPreviewState = ArtifactData & { artifactId: string };

interface ArtifactPreviewProps {
  runId?: string;
  artifactId?: string;
}

export function ArtifactPreview({ runId, artifactId }: ArtifactPreviewProps) {
  const [preview, setPreview] = useState<ArtifactPreviewState | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const tableContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!artifactId || !runId) {
      setPreview(null);
      setPreviewError(null);
      return;
    }

    let cancelled = false;
    setPreview(null);
    setPreviewError(null);

    (async () => {
      try {
        const data = await fetchArtifactData(runId, artifactId);
        if (!cancelled) {
          setPreview({ artifactId, ...data });
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Unknown error";
        if (!cancelled) setPreviewError(msg);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [artifactId, runId]);

  useEffect(() => {
    setSorting([]);
    setGlobalFilter("");
  }, [artifactId, runId]);

  const data = useMemo(
    () => (preview ? preview.rows : []),
    [preview]
  );
  const columns = useMemo<ColumnDef<Record<string, unknown>>[]>(
    () =>
      preview
        ? preview.columns.map((column) => ({
            accessorKey: column,
            header: column,
            cell: (info) => String(info.getValue() ?? ""),
          }))
        : [],
    [preview]
  );

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      globalFilter,
    },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    globalFilterFn: (row, columnId, filterValue) => {
      const value = row.getValue(columnId);
      return String(value ?? "")
        .toLowerCase()
        .includes(String(filterValue ?? "").toLowerCase());
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  const rowModel = table.getRowModel();
  const rowVirtualizer = useVirtualizer({
    count: rowModel.rows.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => 28,
    overscan: 10,
  });
  const virtualRows = rowVirtualizer.getVirtualItems();
  const totalSize = rowVirtualizer.getTotalSize();
  const gridTemplateColumns = table
    .getVisibleLeafColumns()
    .map(() => "minmax(120px, 1fr)")
    .join(" ");

  const filteredCount = rowModel.rows.length;
  const exportedCount = preview?.exported_row_count ?? 0;
  const originalCount = preview?.original_row_count ?? exportedCount;
  const filterActive = globalFilter.trim().length > 0;

  if (!preview && !previewError) return null;

  return (
    <div className="mt-3 bg-gray-50 border border-gray-200 rounded p-3">
      {preview ? (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <div className="text-xs text-gray-600">
              データプレビュー（
              {filterActive ? `${filteredCount}/${exportedCount}` : exportedCount}{" "}
              行 / {preview.columns.length} 列）
              {originalCount > exportedCount && (
                <span className="text-gray-500">
                  {" "}
                  (元 {originalCount} 行)
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <input
                value={globalFilter}
                onChange={(e) => setGlobalFilter(e.target.value)}
                placeholder="Filter rows..."
                className="text-xs border border-gray-300 rounded px-2 py-1 bg-white"
              />
              {globalFilter && (
                <button
                  type="button"
                  onClick={() => setGlobalFilter("")}
                  className="text-xs text-gray-500 hover:text-gray-700"
                >
                  Clear
                </button>
              )}
            </div>
          </div>
          <div
            ref={tableContainerRef}
            className="max-h-[360px] overflow-auto border border-gray-200 rounded bg-white"
          >
            <div className="min-w-full">
              <div className="sticky top-0 z-10 bg-gray-50 border-b">
                {table.getHeaderGroups().map((headerGroup) => (
                  <div
                    key={headerGroup.id}
                    className="grid text-xs font-medium text-gray-700"
                    style={{ gridTemplateColumns }}
                  >
                    {headerGroup.headers.map((header) => {
                      const sort = header.column.getIsSorted();
                      const indicator =
                        sort === "asc" ? "^" : sort === "desc" ? "v" : "";
                      return (
                        <div
                          key={header.id}
                          className="px-2 py-2 border-r border-gray-100 last:border-r-0"
                        >
                          {header.isPlaceholder ? null : (
                            <button
                              type="button"
                              onClick={
                                header.column.getCanSort()
                                  ? header.column.getToggleSortingHandler()
                                  : undefined
                              }
                              className={`flex items-center gap-1 ${
                                header.column.getCanSort()
                                  ? "cursor-pointer select-none"
                                  : "cursor-default"
                              }`}
                            >
                              <span>
                                {flexRender(
                                  header.column.columnDef.header,
                                  header.getContext()
                                )}
                              </span>
                              {indicator && (
                                <span className="text-gray-400">
                                  {indicator}
                                </span>
                              )}
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>

              {rowModel.rows.length === 0 ? (
                <div className="text-xs text-gray-500 px-2 py-3">
                  No rows to display.
                </div>
              ) : (
                <div
                  className="relative"
                  style={{ height: `${totalSize}px` }}
                >
                  {virtualRows.map((virtualRow) => {
                    const row = rowModel.rows[virtualRow.index];
                    return (
                      <div
                        key={row.id}
                        className="absolute left-0 right-0 grid text-xs text-gray-700 border-b border-gray-100"
                        style={{
                          transform: `translateY(${virtualRow.start}px)`,
                          gridTemplateColumns,
                        }}
                      >
                        {row.getVisibleCells().map((cell) => (
                          <div
                            key={cell.id}
                            className="px-2 py-1 border-r border-gray-50 last:border-r-0 truncate"
                          >
                            {flexRender(
                              cell.column.columnDef.cell,
                              cell.getContext()
                            )}
                          </div>
                        ))}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </>
      ) : (
        <div className="text-xs text-gray-500">
          データプレビューを取得できませんでした: {previewError}
        </div>
      )}
    </div>
  );
}
