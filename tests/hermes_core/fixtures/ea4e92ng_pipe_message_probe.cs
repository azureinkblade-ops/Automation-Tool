using System;
using System.Diagnostics;
using System.IO.Pipes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Win32.SafeHandles;

internal static class Ea4e92ngPipeMessageProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        string mode = args[0];
        string name = "ea4e92ng-" + Guid.NewGuid().ToString("N");
        using (var server = new NamedPipeServerStream(
            name, PipeDirection.In, 1, PipeTransmissionMode.Message,
            PipeOptions.Asynchronous))
        using (var release = new ManualResetEventSlim(false))
        {
            Task client = Task.Run(() =>
            {
                using (var connection = new NamedPipeClientStream(
                    ".", name, PipeDirection.Out))
                {
                    connection.Connect(3000);
                    if (mode == "VALID" || mode == "DENY_OBSERVER" ||
                        mode == "KERNEL_MATCH" || mode == "KERNEL_MISMATCH")
                        connection.Write(new byte[] { 1, 2, 3 }, 0, 3);
                    if (mode == "OVERSIZE") connection.Write(new byte[513], 0, 513);
                    if (mode != "DISCONNECT") release.Wait(3000);
                }
            });
            try
            {
                Task accept = server.WaitForConnectionAsync();
                if (!accept.Wait(3000)) return 3;
                byte[] frame;
                Func<SafePipeHandle, string> observer =
                    mode == "NO_OBSERVER" ? null :
                    new Func<SafePipeHandle, string>(handle =>
                    {
                        if (mode == "DENY_OBSERVER")
                            return "CLIENT_IDENTITY_MISMATCH";
                        if (mode == "KERNEL_MATCH" || mode == "KERNEL_MISMATCH")
                        {
                            using (var current = Process.GetCurrentProcess())
                                return Ea4ePipeClientProcessLeaseCandidate.Denial(
                                    handle, (process, pid, creation) =>
                                        pid == (uint)current.Id && creation > 0 &&
                                        mode == "KERNEL_MATCH"
                                            ? null : "CLIENT_IDENTITY_MISMATCH");
                        }
                        return null;
                    });
                string denial = Ea4ePipeChallengeMessageCandidate.CaptureAndObserve(
                    server, 200, observer, out frame);
                string result = denial ?? (frame.Length == 3 && frame[0] == 1
                    ? "BYTES_ONLY" : "WRONG_BYTES");
                Console.WriteLine(result);
                return 0;
            }
            finally
            {
                release.Set();
                try { client.Wait(3000); }
                catch (AggregateException) { }
            }
        }
    }
}
