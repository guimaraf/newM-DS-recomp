#include "recomp_launcher.h"
#include "launcher_profile.h"

#include <windows.h>

#include <array>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>

namespace {
namespace fs = std::filesystem;

constexpr char kKnownSha1[] =
    "a22713711b5cd58dfbafc9688dadea66c59888ce";

struct ModState {
    bool adaptive_widescreen = false;
    bool lock_60fps = true;
    fs::path state_path;
    std::string error;
};

template <size_t N>
void copy_text(char (&target)[N], const char* source) {
    std::snprintf(target, N, "%s", source ? source : "");
}

void load_mod_state(ModState& state) {
    std::ifstream input(state.state_path);
    std::string line;
    while (std::getline(input, line)) {
        if (line == "adaptive_widescreen=1")
            state.adaptive_widescreen = true;
        else if (line == "adaptive_widescreen=0")
            state.adaptive_widescreen = false;
        else if (line == "lock_60fps=1")
            state.lock_60fps = true;
        else if (line == "lock_60fps=0")
            state.lock_60fps = false;
    }
}

void save_mod_state(const ModState& state) {
    std::ofstream output(state.state_path);
    output << "adaptive_widescreen=" << (state.adaptive_widescreen ? "1" : "0") << "\n";
    output << "lock_60fps=" << (state.lock_60fps ? "1" : "0") << "\n";
}

int mod_feature_count(void*) {
    return 2;
}

int mod_feature_get(void* context, int index,
                    RecompLauncherCModFeature* output) {
    if (!context || !output) return 0;
    const auto* state = static_cast<const ModState*>(context);
    std::memset(output, 0, sizeof(*output));
    if (index == 0) {
        copy_text(output->id, "adaptive-widescreen");
        copy_text(output->package_id, "nsmb-adaptive-widescreen");
        copy_text(output->package_version, "0.1.0");
        copy_text(output->package_name, "NSMB Adaptive Widescreen");
        copy_text(output->name, "Adaptive Widescreen");
        copy_text(output->author, "ndsrecomp");
        copy_text(
            output->description,
            "Expands presentation viewport. The bottom touchscreen remains native and clickable.");
        copy_text(output->group, "Display enhancements");
        copy_text(output->status,
                  state->adaptive_widescreen ? "Enabled" : "Disabled");
        output->enabled = state->adaptive_widescreen ? 1 : 0;
        return 1;
    }
    if (index == 1) {
        copy_text(output->id, "lock-60fps");
        copy_text(output->package_id, "nsmb-lock-60fps");
        copy_text(output->package_version, "0.1.0");
        copy_text(output->package_name, "NSMB 60 FPS Limiter");
        copy_text(output->name, "Lock 60 FPS");
        copy_text(output->author, "ndsrecomp");
        copy_text(
            output->description,
            "Locks framerate strictly to hardware DS speed (59.826 Hz / 60 FPS). "
            "Prevents high-refresh-rate monitors (120Hz/144Hz+) from running gameplay too fast.");
        copy_text(output->group, "Display enhancements");
        copy_text(output->status,
                  state->lock_60fps ? "Enabled" : "Disabled");
        output->enabled = state->lock_60fps ? 1 : 0;
        return 1;
    }
    return 0;
}

int mod_feature_option_get(void*, const char*, const char*, int,
                           RecompLauncherCModOption*) {
    return 0;
}

int mod_feature_enable(void* context, const char* package_id,
                       const char* feature_id, int enabled) {
    if (!context || !package_id || !feature_id) return 0;
    auto* state = static_cast<ModState*>(context);
    if (std::strcmp(feature_id, "adaptive-widescreen") == 0) {
        state->adaptive_widescreen = (enabled != 0);
        save_mod_state(*state);
        return 1;
    }
    if (std::strcmp(feature_id, "lock-60fps") == 0) {
        state->lock_60fps = (enabled != 0);
        save_mod_state(*state);
        return 1;
    }
    return 0;
}

int mod_feature_set_option(void*, const char*, const char*, const char*,
                           const char*) {
    return 0;
}

int mod_commit(void* context, const char*) {
    if (!context) return 0;
    auto* state = static_cast<ModState*>(context);
    save_mod_state(*state);
    state->error.clear();
    return 1;
}

const char* mod_last_error(void* context) {
    return context ? static_cast<ModState*>(context)->error.c_str()
                   : "Missing mod state.";
}

RecompLauncherCModProvider make_mod_provider(ModState* state) {
    RecompLauncherCModProvider provider{};
    provider.ctx = state;
    provider.commit = mod_commit;
    provider.last_error = mod_last_error;
    provider.feature_count = mod_feature_count;
    provider.feature_get = mod_feature_get;
    provider.feature_option_get = mod_feature_option_get;
    provider.feature_enable = mod_feature_enable;
    provider.feature_set_option = mod_feature_set_option;
    provider.archive_extension = ".ndsmod";
    provider.archive_description = "Nintendo DS mod package";
    return provider;
}

std::wstring quote(const fs::path& value) {
    return L"\"" + value.wstring() + L"\"";
}

bool launch_runner(const fs::path& game_dir, const std::string& rom_path,
                   int display_layout, bool adaptive,
                   int supersampling, int antialiasing, int renderer,
                   bool mod_lock_60fps) {
    const fs::path runner = game_dir / "New Super Mario Bros DS Decomp Runner.exe";
    const fs::path config = game_dir / "game.toml";
    const fs::path bios = game_dir / "bios";
    const fs::path save_dir = game_dir / "saves";
    const fs::path save = save_dir / "nsmb_usa.sav";

    if (!fs::is_regular_file(runner) || !fs::is_regular_file(config)) {
        MessageBoxW(nullptr,
            L"The release is incomplete: New Super Mario Bros DS Decomp Runner.exe or game.toml is "
            L"missing in this directory.",
            L"New Super Mario Bros DS Decomp", MB_OK | MB_ICONERROR);
        return false;
    }

    std::error_code ec;
    fs::create_directories(bios, ec);
    fs::create_directories(save_dir, ec);

    const bool separate = (display_layout == 0 || display_layout == 2 || adaptive);
    const bool layout_lock_60fps = (display_layout == 0 || display_layout == 1);
    const bool lock_60fps = layout_lock_60fps || mod_lock_60fps;

    const bool no_dumps_mode = true;

    std::wstring command =
        quote(runner) + L" " + quote(bios) +
        L" --interactive --rom " + quote(fs::path(rom_path)) +
        L" --save-path " + quote(save) +
        L" --config " + quote(config) +
        L" --screen-layout " + (separate ? L"separate" : L"stacked") +
        L" --adaptive-widescreen " +
        (adaptive ? L"top" : L"none") +
        L" --supersampling " + std::to_wstring(supersampling) +
        L" --antialiasing " + std::to_wstring(antialiasing) +
        L" --startup-mode automatic";
    if (lock_60fps)
        command += L" --fps-limit 60";
    else
        command += L" --fps-limit 0";
    if (no_dumps_mode)
        command += L" --freebios --generated-firmware --boot direct";

    wchar_t old_path[32768]{};
    GetEnvironmentVariableW(L"PATH", old_path,
                            static_cast<DWORD>(std::size(old_path)));
    const std::wstring path =
        L"C:\\msys64\\mingw64\\bin;" + std::wstring(old_path);
    SetEnvironmentVariableW(L"PATH", path.c_str());
    static constexpr const wchar_t* kRendererPolicies[] = {
        L"auto", L"soft", L"compute",
    };
    const int renderer_index =
        renderer >= 0 && renderer < static_cast<int>(
            std::size(kRendererPolicies)) ? renderer : 0;
    const DWORD old_renderer_size =
        GetEnvironmentVariableW(L"NDS_3D_RENDERER", nullptr, 0);
    std::wstring old_renderer;
    if (old_renderer_size != 0) {
        old_renderer.resize(old_renderer_size);
        GetEnvironmentVariableW(L"NDS_3D_RENDERER",
                                old_renderer.data(), old_renderer_size);
        old_renderer.resize(old_renderer_size - 1u);
    }
    SetEnvironmentVariableW(
        L"NDS_3D_RENDERER", kRendererPolicies[renderer_index]);

    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    const BOOL ok = CreateProcessW(
        runner.wstring().c_str(), command.data(), nullptr, nullptr, FALSE,
        CREATE_NO_WINDOW, nullptr, game_dir.wstring().c_str(),
        &startup, &process);
    SetEnvironmentVariableW(
        L"NDS_3D_RENDERER",
        old_renderer_size != 0 ? old_renderer.c_str() : nullptr);
    if (!ok) {
        std::fprintf(stderr, "CreateProcessW failed: %lu\n",
                     static_cast<unsigned long>(GetLastError()));
        return false;
    }
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return true;
}

}  // namespace

int main(int argc, char** argv) {
    RecompLauncherCSettings settings{};
    settings.output_method = 2;
    settings.window_scale = 3;
    settings.enable_audio = 1;
    settings.audio_freq = 32768;
    settings.volume = 100;
    settings.player_src[0] = 2;
    settings.supersampling = 1;
    settings.antialiasing = 0;
    settings.display_layout = 0;
    settings.renderer = 0;

    static const char* const sha1[] = { kKnownSha1 };
    static const char* const display_layouts[] = {
        "Separate windows (60 FPS)",
        "Stacked window (60 FPS)",
        "Separate windows (Unlocked)",
        "Stacked window (Unlocked)",
    };
    static const char* const renderers[] = {
        "Automatic (OpenGL preferred)",
        "Software",
        "OpenGL 4.3",
    };

    wchar_t exe_path_buf[MAX_PATH]{};
    GetModuleFileNameW(nullptr, exe_path_buf, MAX_PATH);
    const fs::path exe_dir = fs::path(exe_path_buf).parent_path();
    ModState mod_state{};
    mod_state.state_path = exe_dir / "nsmb_mods.ini";
    load_mod_state(mod_state);
    RecompLauncherCModProvider mod_provider = make_mod_provider(&mod_state);

    RecompLauncherCGameInfo game{};
    launcher_profile_apply("nds", &game);
    game.name = "New Super Mario Bros DS Decomp";
    game.region = "USA";
    game.known_sha1_hex = sha1;
    game.num_known_sha1 = std::size(sha1);
    game.lock_device = 0;
    game.hide_rebind = 0;
    game.display_layout_labels = display_layouts;
    game.num_display_layouts = std::size(display_layouts);
    game.has_renderer = 1;
    game.renderer_labels = renderers;
    game.num_renderers = std::size(renderers);
    game.has_vsync = 1;
    game.mods = &mod_provider;

    const fs::path default_rom = exe_dir / "New Super Mario Bros. (USA).nds";
    char selected_rom[1024]{};
    const int result = recomp_launcher_run_window(
        "New Super Mario Bros DS Decomp", &settings, &game,
        exe_dir.string().c_str(), default_rom.string().c_str(),
        selected_rom, sizeof(selected_rom));
    if (result == 1) return 0;
    if (result == 2) {
        std::fprintf(stderr, "recomp-ui unavailable\n");
        return 2;
    }
    return launch_runner(exe_dir, selected_rom, settings.display_layout,
                         mod_state.adaptive_widescreen,
                         settings.supersampling, settings.antialiasing,
                         settings.renderer, mod_state.lock_60fps) ? 0 : 1;
}
