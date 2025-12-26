import { useEffect, useState } from "react";
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

  if (!preview && !previewError) return null;

  return (
    <div className="mt-3 bg-gray-50 border border-gray-200 rounded p-3 overflow-auto">
      {preview ? (
        <>
          <div className="text-xs text-gray-600 mb-2">
            データプレビュー（{preview.exported_row_count} 行 /{" "}
            {preview.columns.length} 列）
          </div>
          <table className="text-xs w-full border-collapse">
            <thead>
              <tr>
                {preview.columns.map((c) => (
                  <th
                    key={c}
                    className="text-left border-b border-gray-200 pr-3 pb-1 font-medium"
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.rows.slice(0, 5).map((row, i) => (
                <tr key={i}>
                  {preview.columns.map((c) => (
                    <td
                      key={c}
                      className="pr-3 py-1 border-b border-gray-100"
                    >
                      {String((row as Record<string, unknown>)[c] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <div className="text-xs text-gray-500">
          データプレビューを取得できませんでした: {previewError}
        </div>
      )}
    </div>
  );
}
