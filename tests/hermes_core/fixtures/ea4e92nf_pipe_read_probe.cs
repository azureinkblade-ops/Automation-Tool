using System;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Threading;
using System.Threading.Tasks;

internal static class Ea4e92nfPipeReadProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        string mode = args[0];
        if (mode != "COMPLETE" && mode != "TIMEOUT" &&
            mode != "PARTIAL" && mode != "DISCONNECT") return 2;

        string name = "ea4e92nf-" + Guid.NewGuid().ToString("N");
        using (var server = new NamedPipeServerStream(
            name, PipeDirection.In, 1, PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous))
        using (var release = new ManualResetEventSlim(false))
        {
            Task client = Task.Run(() =>
            {
                using (var connection = new NamedPipeClientStream(
                    ".", name, PipeDirection.Out))
                {
                    connection.Connect(3000);
                    if (mode == "COMPLETE") connection.WriteByte(0x4e);
                    if (mode == "PARTIAL") connection.WriteByte(0x50);
                    if (mode != "DISCONNECT") release.Wait(3000);
                }
            });
            try
            {
                Task accept = server.WaitForConnectionAsync();
                if (!accept.Wait(3000)) return Report("CONNECT_TIMEOUT", 1);
                byte[] buffer = new byte[2];
                var timer = Stopwatch.StartNew();
                using (var cancellation = new CancellationTokenSource())
                {
                    Task<int> read = server.ReadAsync(
                        buffer, 0, buffer.Length, cancellation.Token);
                    int deadline = mode == "COMPLETE" ? 2000 : 150;
                    if (!read.Wait(deadline))
                    {
                        cancellation.Cancel();
                        server.Dispose();
                        release.Set();
                        if (!WaitForCompletion(read, 2000))
                            return Report("UNOBSERVED_COMPLETION", 1);
                        if (timer.ElapsedMilliseconds > 2500)
                            return Report("CANCEL_OVERRUN", 1);
                        return Report("CANCELED_AND_OBSERVED", 0);
                    }
                    if (mode == "COMPLETE" && read.Result == 1 &&
                        buffer[0] == 0x4e)
                        return Report("ONE_BYTE_READ", 0);
                    if (mode == "PARTIAL" && read.Result == 1 &&
                        buffer[0] == 0x50)
                        return Report("PARTIAL_READ_OBSERVED", 0);
                    if (mode == "DISCONNECT" && read.Result == 0)
                        return Report("EOF_OBSERVED", 0);
                    return Report("UNEXPECTED_READ", 1);
                }
            }
            catch (AggregateException error)
            {
                return Report("READ_EXCEPTION:" +
                    error.InnerException.GetType().Name, 1);
            }
            finally
            {
                release.Set();
                try
                {
                    if (!client.Wait(3000))
                        Console.Error.WriteLine("CLIENT_CLEANUP_TIMEOUT");
                }
                catch (AggregateException error)
                {
                    Console.Error.WriteLine("CLIENT_ERROR:" +
                        error.InnerException.GetType().Name);
                }
            }
        }
    }

    private static bool WaitForCompletion(Task<int> read, int timeout)
    {
        try { return read.Wait(timeout); }
        catch (AggregateException) { return read.IsCompleted; }
    }

    private static int Report(string status, int exitCode)
    {
        Console.WriteLine(status);
        return exitCode;
    }
}
