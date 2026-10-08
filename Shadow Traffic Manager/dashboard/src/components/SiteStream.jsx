import { useEffect } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';

/**
 * SiteStream — invisible "bridge" component that opens and maintains one
 * live WebSocket connection for exactly one site.
 *
 * WHY THIS COMPONENT EXISTS:
 * Previously, App.jsx opened a single WebSocket for only ONE site at a time
 * (whichever was selected, or sites[0] by default). Every other site card on
 * the dashboard grid never received any live telemetry_update messages, so
 * newly added sites (and any card that wasn't the first/selected one) stayed
 * frozen at their initial placeholder values forever — looking like it was
 * "stuck loading."
 *
 * Rendering one <SiteStream> per site (see App.jsx) gives every card its own
 * independent connection, so all sites update live and simultaneously.
 */
export default function SiteStream({ siteId, onMessage, onStatusChange }) {
  const { status } = useWebSocket(siteId, onMessage, Boolean(siteId));

  useEffect(() => {
    if (onStatusChange) onStatusChange(siteId, status);
  }, [siteId, status, onStatusChange]);

  return null; // renders nothing — purely a data connection
}
