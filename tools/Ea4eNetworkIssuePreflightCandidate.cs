// One-process, read-only preflight candidate. This is not an issuer.
using System;
using System.Collections.Generic;
using System.IO;

internal static class Ea4eNetworkIssuePreflightCandidate
{
    private static int Main(string[] args)
    {
        // The request's operator candidate must equal the observed-token target.
        if (args.Length != 12)
        {
            Console.WriteLine("DENY:ARGUMENTS_INVALID");
            return 1;
        }
        if (!String.Equals(args[6], args[0], StringComparison.Ordinal))
        {
            Console.WriteLine("DENY:OPERATOR_BINDING_MISMATCH");
            return 1;
        }
        string tokenDenial = Ea4eOperatorTokenObservation.Denial(args[0]);
        if (tokenDenial != null)
        {
            Console.WriteLine("DENY:" + tokenDenial);
            return 1;
        }
        try
        {
            var labels = new Dictionary<string, string> {
                { "hermes.ea4e.attempt", args[8] },
                { "hermes.ea4e.candidate_sha256", args[9] },
                { "hermes.ea4e.profile", args[10] },
                { "hermes.ea4e.cleanup_owner", args[11] },
            };
            byte[] request = ReadBounded(args[1]);
            bool matches = Ea4eNetworkIssueRequestCandidate.Matches(
                request, args[2], args[3], args[4], args[5], args[6],
                args[7], labels);
            Console.WriteLine(matches ? "MATCH:NON_AUTHORIZING_PREFLIGHT"
                                      : "DENY:REQUEST_BYTES_MISMATCH");
            return matches ? 0 : 1;
        }
        catch (Exception)
        {
            Console.WriteLine("DENY:REQUEST_UNAVAILABLE");
            return 1;
        }
    }

    private static byte[] ReadBounded(string path)
    {
        using (var stream = new FileStream(
            path, FileMode.Open, FileAccess.Read, FileShare.None))
        {
            if (stream.Length < 1 || stream.Length > 16384)
                throw new InvalidDataException("Request size denied");
            var bytes = new byte[(int)stream.Length];
            int offset = 0;
            while (offset < bytes.Length)
            {
                int count = stream.Read(bytes, offset, bytes.Length - offset);
                if (count == 0)
                    throw new EndOfStreamException();
                offset += count;
            }
            if (stream.ReadByte() != -1)
                throw new InvalidDataException("Request changed during read");
            return bytes;
        }
    }
}
