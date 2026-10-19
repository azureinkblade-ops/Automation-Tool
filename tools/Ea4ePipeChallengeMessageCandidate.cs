using System;
using System.IO.Pipes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Win32.SafeHandles;

// Captures bytes from an already connected pipe; it grants no identity or authority.
internal static class Ea4ePipeChallengeMessageCandidate
{
    internal static string CaptureAndObserve(
        NamedPipeServerStream pipe, int deadlineMilliseconds,
        Func<SafePipeHandle, string> observe, out byte[] frame)
    {
        frame = null;
        if (observe == null) return "CLIENT_OBSERVER_UNAVAILABLE";
        byte[] captured;
        string denial = Capture(pipe, deadlineMilliseconds, out captured);
        if (denial != null) return denial;
        if (!pipe.IsConnected || pipe.SafePipeHandle.IsClosed ||
            pipe.SafePipeHandle.IsInvalid) return "CLIENT_CONNECTION_LOST";
        try { denial = observe(pipe.SafePipeHandle); }
        catch (Exception) { return "CLIENT_OBSERVATION_FAILED"; }
        if (denial != null) return denial;
        if (!pipe.IsConnected) return "CLIENT_CONNECTION_LOST";
        frame = captured;
        return null;
    }

    internal static string Capture(
        NamedPipeServerStream pipe, int deadlineMilliseconds, out byte[] frame)
    {
        frame = null;
        if (pipe == null || !pipe.IsConnected ||
            pipe.TransmissionMode != PipeTransmissionMode.Message ||
            pipe.ReadMode != PipeTransmissionMode.Message ||
            deadlineMilliseconds < 1 || deadlineMilliseconds > 5000)
            return "PIPE_CONTRACT_INVALID";

        byte[] buffer = new byte[513];
        using (var cancellation = new CancellationTokenSource())
        {
            Task<int> read;
            try { read = pipe.ReadAsync(buffer, 0, buffer.Length, cancellation.Token); }
            catch (Exception) { return "READ_START_FAILED"; }
            try
            {
                if (!read.Wait(deadlineMilliseconds))
                {
                    cancellation.Cancel();
                    pipe.Dispose();
                    try { read.Wait(2000); }
                    catch (AggregateException) { }
                    return read.IsCompleted
                        ? "READ_DEADLINE_EXCEEDED" : "READ_COMPLETION_UNKNOWN";
                }
                int size = read.Result;
                if (size == 0) return "CLIENT_DISCONNECTED";
                if (size > 512 || !pipe.IsMessageComplete)
                    return "FRAME_SIZE_OR_BOUNDARY_INVALID";
                frame = new byte[size];
                Buffer.BlockCopy(buffer, 0, frame, 0, size);
                return null;
            }
            catch (AggregateException) { return "READ_FAILED"; }
            catch (ObjectDisposedException) { return "PIPE_DISPOSED"; }
            catch (InvalidOperationException) { return "PIPE_STATE_INVALID"; }
        }
    }
}
