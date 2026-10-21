"""Measure an existing runner without building or touching the player's save.

Routes are JSON arrays of {name, frames, keys: [SDL key names]} segments.
Timing samples are windows between TCP queries, NOT individual frame times.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time


def digest(path, algorithm):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument('--runner', type=Path, default=root / 'dist-playable/New Super Mario Bros DS Decomp Runner.exe')
    parser.add_argument('--rom', type=Path, default=root / 'dist-playable/New Super Mario Bros. (USA).nds')
    parser.add_argument('--route', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--port', type=int, default=21385)
    parser.add_argument('--poll', type=float, default=0.25)
    args = parser.parse_args()
    if args.poll <= 0:
        parser.error('--poll must be positive')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    route = json.loads(args.route.read_text()) if args.route else [dict(name='title', frames=900)]
    command = [str(args.runner.resolve()), str(root / 'dist-playable/bios'),
               '--interactive', '--rom', str(args.rom.resolve()), '--boot', 'direct',
               '--freebios', '--generated-firmware', '--no-save',
               '--identity-mac', '02:00:00:00:00:01', '--fps-limit', '60',
               '--screen-layout', 'stacked', '--diagnostics', 'on',
               '--diagnostics-dir', str(out), '--coverage-manifest', str(out / 'coverage.json'),
               '--port', str(args.port)]
    metadata = dict(command=command, route=route, poll_seconds=args.poll,
                    runner_sha256=digest(args.runner, 'sha256'),
                    rom_sha1=digest(args.rom, 'sha1'),
                    timing='TCP sample windows; no per-frame percentiles')
    (out / 'metadata.json').write_text(json.dumps(metadata, indent=2))
    env = os.environ.copy()
    env['PATH'] = r'C:\msys64\mingw64\bin;' + env['PATH']
    env['NDS_FRONTEND_STATS'] = '1'
    env['NDS_FRONTEND_MAX_FRAMES'] = str(sum(s['frames'] for s in route) + 3000)
    connection = None
    with (out / 'runner.log').open('w') as log, (out / 'samples.jsonl').open('w') as samples:
        proc = subprocess.Popen(command, cwd=out, env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 60
            while connection is None:
                if proc.poll() is not None:
                    raise RuntimeError(f'Runner exited: {proc.returncode}; see {out / "runner.log"}')
                try:
                    connection = socket.create_connection(('127.0.0.1', args.port), timeout=1)
                except PermissionError:
                    # A denied loopback socket is not a slow runner startup.
                    raise
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Debug server did not start')
                    time.sleep(0.1)
            connection.settimeout(30)
            stream = connection.makefile('rwb')

            def request(cmd, **kwargs):
                stream.write((json.dumps(dict(cmd=cmd, **kwargs)) + '\n').encode())
                stream.flush()
                line = stream.readline()
                if not line:
                    raise RuntimeError('Runner disconnected')
                response = json.loads(line)
                if 'error' in response:
                    raise RuntimeError(response)
                return response

            held = set()
            results = []

            def key_event(key, down):
                if not request('frontend_input', action='key', key=key, down=down).get('ok'):
                    raise RuntimeError(f'Key injection failed: {key}, down={down}')

            for index, segment in enumerate(route):
                keys = set(segment.get('keys', []))
                for key in sorted(held - keys):
                    key_event(key, False)
                for key in sorted(keys - held):
                    key_event(key, True)
                held = keys
                before = request('frontend_stats')
                first = before
                state_before = request('static_coverage')
                start = time.monotonic()
                while before['frames'] - first['frames'] < segment['frames']:
                    if time.monotonic() - start > max(60, segment['frames'] / 5):
                        raise TimeoutError(f'Segment stalled: {segment["name"]}')
                    time.sleep(args.poll)
                    after = request('frontend_stats')
                    frames = after['frames'] - before['frames']
                    elapsed = (after['now_ticks'] - before['now_ticks']) / after['freq']
                    sample = dict(segment=segment['name'], frames=after['frames'],
                                  frame_delta=frames, seconds=elapsed,
                                  fps=frames / elapsed if elapsed else 0,
                                  underruns=after['underruns'] - before['underruns'])
                    sample['ms_per_frame'] = {
                        k.removesuffix('_ticks'): (after[k] - before[k]) * 1000 / after['freq'] / frames
                        for k in ('emu_ticks', 'present_ticks', 'drain_ticks') if frames}
                    samples.write(json.dumps(sample) + '\n')
                    samples.flush()
                    before = after
                result = dict(name=segment['name'], requested_frames=segment['frames'],
                              keys=sorted(keys), before=first, after=before,
                              coverage_before=state_before, coverage_after=request('static_coverage'),
                              dispatch=request('dispatch_stats'), profile=request('profile'))
                results.append(result)
                request('framebuffer_sync')
                time.sleep(0.1)
                for engine in ('A', 'B'):
                    fb = request('framebuffer', engine=engine)
                    filename = out / f'{index:02d}-{segment["name"]}-{engine}.ppm'
                    filename.write_bytes(f'P6\n{fb["w"]} {fb["h"]}\n255\n'.encode() + bytes.fromhex(fb['rgb']))
                (out / 'segments.json').write_text(json.dumps(results, indent=2))
                frames = before['frames'] - first['frames']
                seconds = (before['now_ticks'] - first['now_ticks']) / before['freq']
                print(f'{segment["name"]}: {frames} frames / {seconds:.3f}s = {frames / seconds:.3f} FPS', flush=True)
            for key in sorted(held):
                key_event(key, False)
            (out / 'scheduler-state.json').write_text(json.dumps(request('scheduler_state'), indent=2))
            request('frontend_exit')
            stream.close()
            connection.close()
            connection = None
            code = proc.wait(timeout=30)
            if code:
                raise RuntimeError(f'Runner exit code {code}')
        finally:
            if connection:
                connection.close()
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=10)


if __name__ == '__main__':
    main()
