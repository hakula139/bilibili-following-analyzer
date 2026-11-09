# ==============================================================================
# Bilibili Following Analyzer Development Flake
# ==============================================================================

{
  description = "Bilibili following analyzer development environment";

  # ----------------------------------------------------------------------------
  # Inputs
  # ----------------------------------------------------------------------------
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    devkit = {
      url = "github:hakula139/devkit/v2";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  # ----------------------------------------------------------------------------
  # Outputs
  # ----------------------------------------------------------------------------
  outputs =
    {
      nixpkgs,
      devkit,
      ...
    }:
    devkit.lib.eachSystem [ "aarch64-darwin" "x86_64-linux" ] (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        dk = devkit.lib.mkLib pkgs;

        # ----------------------------------------------------------------------
        # Python environment
        # ----------------------------------------------------------------------
        pythonEnvironment = {
          packages = with pkgs; [
            python313
            uv
          ];
          UV_PYTHON_DOWNLOADS = "never";
        };

        # ----------------------------------------------------------------------
        # Pre-commit hooks
        # ----------------------------------------------------------------------
        preCommit = dk.preCommit {
          src = ./.;
          hooks = {
            actionlint.enable = true;
            check-yaml.enable = true;
            cspell.enable = true;
            deadnix.enable = true;
            dprint.enable = true;
            markdownlint-cli2.enable = true;
            nixfmt.enable = true;
            prettier.enable = true;
            ruff.enable = true;
            ruff-format.enable = true;
            shellcheck.enable = true;
            shfmt.enable = true;
            sort-file-contents.enable = true;
            statix.enable = true;
            taplo.enable = true;

            bandit =
              let
                package = pkgs.python313Packages.bandit;
              in
              {
                enable = true;
                inherit package;
                entry = pkgs.lib.getExe' package "bandit";
                files = "^bilibili_following_analyzer/.*\\.py$";
              };
          };

          devHooks.mypy = {
            enable = true;
            package = dk.uvTool "mypy";
            pass_filenames = false;
          };
        };
      in
      {
        checks.pre-commit = preCommit.check;

        devShells.python = pkgs.mkShell pythonEnvironment;

        devShells.default = pkgs.mkShell (
          pythonEnvironment
          // {
            inputsFrom = [ preCommit.shell ];
          }
        );

        formatter = pkgs.nixfmt-tree;
      }
    );
}
