"use client";

import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T, i: number) => string;
  emptyMessage?: string;
}

export default function DataTable<T>({
  columns,
  rows,
  rowKey,
  emptyMessage,
}: DataTableProps<T>) {
  return (
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[40rem] text-left text-sm">
        <thead>
          <tr className="border-b divider">
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                className={`px-4 py-3 font-semibold text-[var(--muted)] ${c.className ?? ""}`}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={rowKey(row, i)}
              className="border-b divider last:border-0 transition-colors hover:bg-[var(--surface-2)]/50"
            >
              {columns.map((c) => (
                <td key={c.key} className={`px-4 py-3 ${c.className ?? ""}`}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td
                colSpan={columns.length}
                className="px-4 py-10 text-center text-[var(--muted)]"
              >
                {emptyMessage ?? "—"}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
