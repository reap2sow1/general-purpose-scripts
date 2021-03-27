#!/usr/bin/env python3
# Standard Library Imports
import subprocess
import shutil
import sys
import re
import traceback
import os
import pathlib
import argparse
from os.path import realpath

# Third Party Imports
import ruamel.yaml
import toml
from ruamel.yaml.scalarstring import FoldedScalarString as folded

# Local Application Imports

# general program configurations

PROGRAM_NAME = os.path.basename(sys.path[0])
PROGRAM_ROOT = os.getcwd()


class CustomHelpFormatter(argparse.HelpFormatter):
    def _format_action_invocation(self, action):
        if not action.option_strings:
            default = self._get_default_metavar_for_positional(action)
            (metavar,) = self._metavar_formatter(action, default)(1)
            return metavar

        else:
            parts = []

            # if the Optional doesn't take a value, format is:
            #    -s, --long
            if action.nargs == 0:
                parts.extend(action.option_strings)

            # if the Optional takes a value, formats are:
            #    -s, --long=ARG(S) ==> if both short/long
            #    --long=ARG(S) ==> if just long
            #    -s=ARG(S) ==> if just short
            else:
                default = self._get_default_metavar_for_optional(action)
                args_string = self._format_args(action, default)
                for option_string in action.option_strings:
                    if option_string == action.option_strings[-1]:
                        parts.append(f"{option_string}={args_string}")
                    else:
                        parts.append(option_string)

            return ", ".join(parts)


class JenkinsConfigurationAsCode:

    # jenkins configurations as code (CasC) specifics

    JOB_DSL_ROOT_KEY_YAML = "jobs"
    JOB_DSL_SCRIPT_KEY_YAML = "script"
    JOB_DSL_FILENAME_REGEX = ".*job-dsl.*"
    CASC_JENKINS_CONFIG_PATH = (
        f"{PROGRAM_ROOT}/casc.yaml"  # os.environ["CASC_JENKINS_CONFIG"]
    )
    MODIFIED_CASC_JENKINS_CONFIG_PATH = (
        f"{PROGRAM_ROOT}/mod_{os.path.basename(CASC_JENKINS_CONFIG_PATH)}"
    )
    # readFileFromWorkspace('./foo')
    READ_FILE_FROM_WORKSPACE_EXPRESSION_REGEX = (
        r"readFileFromWorkspace\(.+\)(?=\))"
    )
    # readFileFromWorkspace('./foo') ==> ./foo
    READ_FILE_FROM_WORKSPACE_ARGUMENT_REGEX = (
        r"(?<=readFileFromWorkspace\(').+(?='\))"
    )

    # repo configurations

    GIT_CONFIG_FILE = "jobs.toml"
    GIT_REPOS = toml.load(GIT_CONFIG_FILE)["git"]["repo_urls"]
    GIT_REPOS_DIR_PATH = f"{PROGRAM_ROOT}/git_repos"

    # subcommands labels

    SUBCOMMAND = "subcommand"
    ADDJOBS_SUBCOMMAND = "addjobs"
    PREPARE_REPOS = "prepare_repos"
    PREPARE_REPOS_CLI_NAME = PREPARE_REPOS.replace("_", "-")

    # positional/optional argument labels
    # used at the command line and to reference values of arguments

    # replace(old, new)
    CASC_PATH_SHORT_OPTION = "c"
    CASC_PATH_LONG_OPTION = "casc_path"
    CASC_PATH_LONG_OPTION_CLI_NAME = CASC_PATH_LONG_OPTION.replace("_", "-")
    TRANSFORM_READ_FILE_FROM_WORKSPACE_SHORT_OPTION = "t"
    TRANSFORM_READ_FILE_FROM_WORKSPACE_LONG_OPTION = "transform_rffw"
    TRANSFORM_READ_FILE_FROM_WORKSPACE_CLI_NAME = (
        TRANSFORM_READ_FILE_FROM_WORKSPACE_LONG_OPTION.replace("_", "-")
    )

    # class specific misc

    REPOS_TO_TRANSFER_DIR = "/projects/"
    PWD_IDENTIFER_REGEX = r"\.\/"
    DEFAULT_STDOUT_FD = sys.stdout
    YAML_PARSER_WIDTH = 1000
    OTHER_PROGRAMS_NEEDED = ["git", "find", "docker"]

    _DESC = """Description: A small utility to aid in the construction of Jenkins containers."""
    _arg_parser = argparse.ArgumentParser(
        description=_DESC,
        allow_abbrev=False,
    )
    _arg_subparsers = _arg_parser.add_subparsers(
        title=f"{SUBCOMMAND}s",
        metavar=f"{SUBCOMMAND}s [options ...]",
        dest=SUBCOMMAND,
    )
    _arg_subparsers.required = True

    def __init__(self):

        self.repo_names = list()
        self.casc = ruamel.yaml.comments.CommentedMap()
        self._yaml_parser = ruamel.yaml.YAML()
        self._yaml_parser.width = self.YAML_PARSER_WIDTH

    @classmethod
    def retrieve_cmd_args(cls):
        """How arguments are retrieved from the command line.

        Returns
        -------
        Namespace
            An object that holds attributes pulled from the command line.

        Raises
        ------
        SystemExit
            If user input is not considered valid when parsing arguments.

        """
        try:
            # addjobs
            # NOTE: max_help_position is increased (default is 24)
            # to allow arguments/options help messages be more indented
            # reference:
            # https://stackoverflow.com/questions/46554084/how-to-reduce-indentation-level-of-argument-help-in-argparse
            addjobs = cls._arg_subparsers.add_parser(
                cls.ADDJOBS_SUBCOMMAND,
                help=f"will add Jenkins jobs to loaded configuration based on job-dsl file(s) in repo(s)",
                formatter_class=lambda prog: CustomHelpFormatter(
                    prog, max_help_position=35
                ),
                allow_abbrev=False,
            )
            addjobs.add_argument(
                f"-{cls.CASC_PATH_SHORT_OPTION}",
                f"--{cls.CASC_PATH_LONG_OPTION_CLI_NAME}",
                help="load custom casc instead from CASC_JENKINS_CONFIG",
                metavar="CASC_PATH",
            )
            addjobs.add_argument(
                f"-{cls.TRANSFORM_READ_FILE_FROM_WORKSPACE_SHORT_OPTION}",
                f"--{cls.TRANSFORM_READ_FILE_FROM_WORKSPACE_CLI_NAME}",
                action="store_true",
                help="transform readFileFromWorkspace functions to enable usage with casc && job-dsl plugin",
            )
            # addrepos
            # TODO(conner@conneracrosby.tech): Implement
            addrepos = cls._arg_subparsers.add_parser(
                cls.ADDJOBS_SUBCOMMAND,
                help=f"will add Jenkins jobs to loaded configuration based on job-dsl file(s) in repo(s)",
                formatter_class=lambda prog: CustomHelpFormatter(
                    prog, max_help_position=35
                ),
                allow_abbrev=False,
            )

            args = vars(cls._arg_parser.parse_args())
            return args
        except SystemExit:
            sys.exit(1)

    @classmethod
    def _have_other_programs(cls):
        """Checks if certain programs can be found on the PATH.

        Returns
        -------
        bool
            If all the specified programs could be found.

        See Also
        --------
        OTHER_PROGRAMS_NEEDED

        """
        for prog in cls.OTHER_PROGRAMS_NEEDED:
            if shutil.which(prog) is None:
                print(f"{PROGRAM_NAME}: {prog} cannot be found on the PATH!")
                return False

        return True

    def _load_git_repos(self):
        """Fetches/clones git repos, at least those listed in GIT_REPOS.

        These git repos will be placed into the directory from
        the path ==> GIT_REPOS_DIR_PATH.

        Raises
        ------
        subprocess.CalledProcessError
            If the git client program has issues when
            running.
        PermissionError
            If the user running the command does not have write
            permissions to GIT_REPOS_DIR_PATH.

        See Also
        --------
        GIT_REPOS
        GIT_REPOS_DIR_PATH

        """
        # so I remember, finally always executes
        # from try-except-else-finally block.
        try:
            os.mkdir(self.GIT_REPOS_DIR_PATH)
            os.chdir(self.GIT_REPOS_DIR_PATH)
            for repo_url in self.GIT_REPOS:
                repo_name = os.path.basename(repo_url)
                completed_process = subprocess.run(
                    ["git", "clone", "--quiet", repo_url, repo_name],
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    encoding="utf-8",
                    check=True,
                )
        except subprocess.CalledProcessError:
            print(completed_process.stderr.strip())
            raise
        except PermissionError:
            raise
        else:
            self.repo_names = os.listdir()
        finally:
            os.chdir("..")

    def _load_casc(self, casc_path=CASC_JENKINS_CONFIG_PATH):
        """"""
        # TODO(conner@conneracrosby.tech): Implement
        with open(casc_path, "r") as yaml_f:
            self.casc = self._yaml_parser.load(yaml_f)

    @classmethod
    def _find_job_dsl_file(cls):
        """Locates job-dsl files in the PWD using regex.

        Returns
        -------
        job_dsl_files: list of str
            The job-dsl files found.

        Raises
        ------
        subprocess.CalledProcessError
            Incase the program used to find job-dsl files has an issue.

        See Also
        --------
        JOB_DSL_FILENAME_REGEX

        """
        completed_process = subprocess.run(
            [
                "find",
                ".",
                "-regextype",
                "sed",
                "-maxdepth",
                "1",
                "-regex",
                cls.JOB_DSL_FILENAME_REGEX,
            ],
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            encoding="utf-8",
            check=True,
        )
        # everything but the last index, as it is just ''
        # NOTE: while the func name assumes one file will be returned
        # its possible more than one can be returned
        job_dsl_files = completed_process.stdout.split("\n")[:-1]
        return job_dsl_files

    @staticmethod
    def _meets_job_dsl_filereqs(repo_name, job_dsl_files):
        """Checks if the found job-dsl files meet specific requirements.

        Should note this is solely program specific and not
        related to the limitations/restrictions of the plugin itself.

        Returns
        -------
        bool
            If all the job-dsl files meet the program requirements.

        """
        num_of_job_dsls = len(job_dsl_files)
        if num_of_job_dsls == 0:
            print(
                f"{PROGRAM_NAME}: {repo_name} does not have a job-dsl file, skip"
            )
            return False
        elif num_of_job_dsls > 1:
            # there should be no ambiguity in what job-dsl script to run
            # NOTE: this is open to change
            print(
                f"{PROGRAM_NAME}: {repo_name} has more than one job-dsl file, skip!"
            )
            return False
        else:
            return True

    def _transform_rffw(self, repo_name, job_dsl_fc):
        # assuming the job-dsl created also assumes the PWD == WORKSPACE
        def _transform_workspace_path(rffw_arg):

            return re.sub(
                self.PWD_IDENTIFER_REGEX,
                f"{self.REPOS_TO_TRANSFER_DIR}{repo_name}/",
                rffw_arg,
            )

        rffw_args = dict()
        for rffw_arg in re.findall(
            self.READ_FILE_FROM_WORKSPACE_ARGUMENT_REGEX, job_dsl_fc
        ):
            rffw_args[rffw_arg] = _transform_workspace_path(rffw_arg)
        for rffw_arg, t_rffw_arg in rffw_args.items():
            job_dsl_fc = re.sub(
                rffw_arg,
                t_rffw_arg,
                job_dsl_fc,
            )
        return job_dsl_fc

    def _addjobs(self, t_rffw):
        """"""
        # TODO(conner@conneracrosby.tech): Implement
        os.chdir(self.GIT_REPOS_DIR_PATH)
        for repo_name in self.repo_names:
            try:
                os.chdir(repo_name)
                job_dsl_filenames = self._find_job_dsl_file()
                if not self._meets_job_dsl_filereqs(
                    repo_name, job_dsl_filenames
                ):
                    os.chdir("..")
                    shutil.rmtree(repo_name)
                    continue
                job_dsl_filename = job_dsl_filenames[0]

                # read in the job_dsl file, fc == filecontents
                with open(job_dsl_filename, "r") as job_dsl_fh:
                    job_dsl_fc = job_dsl_fh.read()
                if t_rffw:
                    job_dsl_fc = self._transform_rffw(repo_name, job_dsl_fc)
                # TODO(conner@conneracrosby.tech): Add for ability for 'file' entry to be added vs script' ???
                # NOTE: inspired from:
                # https://stackoverflow.com/questions/35433838/how-to-dump-a-folded-scalar-to-yaml-in-python-using-ruamel
                # ffc == foldedfile-contents
                job_dsl_ffc = folded(job_dsl_fc)
                # NOTE2: this handles the situation for multiple job-dsls:
                # create the 'JOB_DSL_SCRIPT_KEY_YAML: job_dsl_ffc' then
                # either merge into JOB_DSL_ROOT_KEY_YAML
                # or create the JOB_DSL_ROOT_KEY_YAML entry and append to it
                if self.JOB_DSL_ROOT_KEY_YAML in self.casc:
                    self.casc[self.JOB_DSL_ROOT_KEY_YAML].append(
                        dict([(self.JOB_DSL_SCRIPT_KEY_YAML, job_dsl_ffc)])
                    )
                else:
                    script_entry = dict(
                        [(self.JOB_DSL_SCRIPT_KEY_YAML, job_dsl_ffc)]
                    )
                    self.casc[self.JOB_DSL_ROOT_KEY_YAML] = [script_entry]
            except PermissionError:
                raise

    def main(self, cmd_args):
        """The main of the program."""
        if not self._have_other_programs():
            sys.exit(1)
        try:
            if cmd_args[self.SUBCOMMAND] == self.ADDJOBS_SUBCOMMAND:
                self._load_git_repos()
                self._load_casc(cmd_args[self.CASC_PATH_LONG_OPTION])
                self._addjobs(
                    cmd_args[
                        self.TRANSFORM_READ_FILE_FROM_WORKSPACE_LONG_OPTION
                    ]
                )
                self._yaml_parser.dump(self.casc, self.DEFAULT_STDOUT_FD)
                sys.exit(0)
        except (subprocess.CalledProcessError, SystemExit):
            sys.exit(1)
        except PermissionError as e:
            print(
                f"{PROGRAM_NAME}: a particular file/path was unaccessible, {realpath(e)}"
            )
            sys.exit(1)
        except Exception as e:
            traceback.print_exception(type(e), e, e.__traceback__)
            print(f"{PROGRAM_NAME}: an unknown error occurred, see the above!")
            sys.exit(1)
        finally:
            if pathlib.Path(self.GIT_REPOS_DIR_PATH).exists():
                shutil.rmtree(self.GIT_REPOS_DIR_PATH)


if __name__ == "__main__":
    jcasc = JenkinsConfigurationAsCode()
    args = jcasc.retrieve_cmd_args()
    jcasc.main(args)
