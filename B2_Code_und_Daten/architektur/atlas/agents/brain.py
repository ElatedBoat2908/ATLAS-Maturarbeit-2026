from pathlib import Path
from atlas.skills.project_scanner import save_scan_report
from atlas.skills.project_summary import save_summary
from atlas.skills.data_scanner import save_data_scan


class AtlasBrain:

    def __init__(self):
        self.project_root = Path(__file__).resolve().parents[2]

    def think(self, task: str):

        print(f"\n ATLAS received task:\n{task}\n")

        if "scan" in task.lower():

            print(" Running Project Scanner...")
            save_scan_report()

            print(" Building Project Summary...")
            save_summary()

            print(" Project indexed.\n")

        elif "data" in task.lower():

            print(" Running Data Scanner...")
            save_data_scan()

            print(" Data indexed.\n")

        else:

            print("I don't know yet which skill I should use.")


if __name__ == "__main__":

    atlas = AtlasBrain()

    atlas.think("scan project")