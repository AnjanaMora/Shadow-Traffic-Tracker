import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * Robust WebSocket hook for streaming live telemetry and predictions.
 * Automatically handles reconnection with exponential backoff and heartbeat pings.
 *
 * @param {string} siteId - Target monitored site ID
 * @param {function} onMessage - Callback invoked on receiving parsed JSON frame
 * @param {boolean} enabled - Whether socket connection should be active
 */
export function useWebSocket(siteId, onMessage, enabled = true) {
  const [status, setStatus] = useState('disconnected'); // 'connecting' | 'connected' | 'reconnecting' | 'disconnected'
  const [lastHeartbeat, setLastHeartbeat] = useState(null);
  const [reconnectCount, setReconnectCount] = useState(0);

  const socketRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const pingIntervalRef = useRef(null);
  const onMessageRef = useRef(onMessage);

  // Keep latest onMessage callback reference
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const connect = useCallback(() => {
    if (!enabled || !siteId) {
      setStatus('disconnected');
      return;
    }

    // Clean up any pending reconnect
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Clean up existing socket
    if (socketRef.current) {
      try {
        socketRef.current.close();
      } catch {
        // ignore
      }
      socketRef.current = null;
    }

    setStatus((prev) => (prev === 'disconnected' ? 'connecting' : 'reconnecting'));

    // Construct WebSocket URL matching current host
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/live/${encodeURIComponent(siteId)}`;

    try {
      const ws = new WebSocket(wsUrl);
      socketRef.current = ws;

      ws.onopen = () => {
        setStatus('connected');
        setReconnectCount(0);

        // Start heartbeat ping
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
            setLastHeartbeat(Date.now());
          }
        }, 15000);
      };

      ws.onmessage = (event) => {
        if (event.data === 'pong') {
          setLastHeartbeat(Date.now());
          return;
        }

        try {
          const parsed = JSON.parse(event.data);
          if (onMessageRef.current) {
            onMessageRef.current(parsed);
          }
        } catch {
          // Non-JSON message or raw text
        }
      };

      ws.onerror = () => {
        // ws.onclose will handle reconnect
      };

      ws.onclose = (event) => {
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = null;
        }

        // Only auto-reconnect if socket wasn't intentionally closed (code 1000)
        if (enabled && event.code !== 1000) {
          setStatus('reconnecting');
          setReconnectCount((prev) => {
            const nextCount = prev + 1;
            // Exponential backoff: 1s, 2s, 3s... max 10s
            const delay = Math.min(1000 * Math.pow(1.5, Math.min(nextCount, 6)), 10000);
            reconnectTimeoutRef.current = setTimeout(() => {
              connect();
            }, delay);
            return nextCount;
          });
        } else {
          setStatus('disconnected');
        }
      };
    } catch {
      setStatus('reconnecting');
      reconnectTimeoutRef.current = setTimeout(connect, 3000);
    }
  }, [siteId, enabled]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
      if (socketRef.current) {
        socketRef.current.close(1000, 'Component unmounted');
        socketRef.current = null;
      }
      setStatus('disconnected');
    };
  }, [connect]);

  const send = useCallback((data) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(typeof data === 'string' ? data : JSON.stringify(data));
      return true;
    }
    return false;
  }, []);

  return {
    status,
    isConnected: status === 'connected',
    isReconnecting: status === 'reconnecting',
    reconnectCount,
    lastHeartbeat,
    reconnect: connect,
    send,
  };
}
