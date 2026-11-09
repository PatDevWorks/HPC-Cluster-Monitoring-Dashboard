import React, { useEffect, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';

export default function ConfirmModal({
  open,
  title,
  description,
  confirmLabel = 'Confirm Action',
  variant = 'warning',
  requireReason = false,
  defaultReason = '',
  nodePickerOptions = null,
  onConfirm,
  onCancel,
}) {
  const [reason, setReason] = useState(defaultReason);
  const [pickedNode, setPickedNode] = useState('');

  useEffect(() => {
    setReason(defaultReason || '');
    if (nodePickerOptions && nodePickerOptions.length > 0) {
      setPickedNode(nodePickerOptions[0].node_id);
    }
  }, [open, defaultReason, nodePickerOptions]);

  if (!open) return null;

  const btnColors =
    variant === 'danger'
      ? 'bg-rose-600 hover:bg-rose-500 text-white'
      : 'bg-amber-500 hover:bg-amber-400 text-slate-950';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-4 backdrop-blur-xs">
      <div className="spu-card w-full max-w-md p-5">
        <div className="flex items-start justify-between gap-3 border-b pb-3 spu-border">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-500/15 text-amber-400">
              <AlertTriangle className="h-5 w-5" />
            </div>
            <h3 className="text-sm font-bold">{title}</h3>
          </div>
          <button
            onClick={onCancel}
            className="rounded-lg p-1 spu-text-secondary hover:bg-[var(--bg-hover)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <p className="mt-3 text-xs leading-relaxed spu-text-secondary">{description}</p>

        {nodePickerOptions && nodePickerOptions.length > 0 && (
          <div className="mt-3">
            <label className="block text-xs font-semibold mb-1">Target Compute Node</label>
            <select
              value={pickedNode}
              onChange={(e) => setPickedNode(e.target.value)}
              className="spu-input w-full"
            >
              {nodePickerOptions.map((n) => (
                <option key={n.node_id} value={n.node_id}>
                  {n.display_name || n.node_id} ({n.ip}) — {n.slurm_state}
                </option>
              ))}
            </select>
          </div>
        )}

        {requireReason && (
          <div className="mt-3">
            <label className="block text-xs font-semibold mb-1">
              Administrative Audit Reason
            </label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Enter reason recorded in Slurm & audit log..."
              className="spu-input w-full"
            />
          </div>
        )}

        <div className="mt-5 flex items-center justify-end gap-2">
          <button onClick={onCancel} className="spu-btn-secondary">
            Cancel
          </button>
          <button
            onClick={() => onConfirm({ reason, nodeId: pickedNode })}
            className={`rounded-lg px-3.5 py-2 text-xs font-bold transition ${btnColors}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
