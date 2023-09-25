import json
from typing import Dict, Any
import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import os
import time
from pandas import DataFrame

# set backend to agg since matplotlib is not running in main thread
matplotlib.use('Agg')

# dark background plots
plt.style.use('dark_background')

# default replay dir
replay_dir = 'C:/SteamLibrary/steamapps/common/Street Fighter 6/'

# recent replay filename
replay_name = 'recent_replay.json'

# load character id to name str mappings
with open(f"data/character_ids.json", 'r') as f:
    character_ids = json.load(f)

# load act_st id to string mappings
with open(f"data/act_st.json", 'r') as f:
    act_st_names = json.load(f)

# character move name paths
character_move_names_path = "data/fixed_character_names"

# create stat_img directory if it doesn't exist
os.makedirs("stats_img", exist_ok=True)


def watch_file_for_changes(filename, poll_interval=1.0):
    # initial timestamp
    initial_timestamp = os.path.getmtime(filename)

    while True:
        # wait for the poll interval
        time.sleep(poll_interval)

        # check the current timestamp
        current_timestamp = os.path.getmtime(filename)

        # if the timestamp has changed, exit
        if current_timestamp != initial_timestamp:
            break


def load_recent_file(sf6_path: str) -> tuple[dict[Any, DataFrame], dict[str, Any]]:
    # columns from the replay data to keep
    keep_columns = {
        'current_HP': int,
        'blockstun': int,
        'mActionId': int,
        'hitstun': int,
        'act_st': int,
        'drive': float
    }

    loaded_file = False
    while not loaded_file:
        try:
            # load the replay file
            with open(f"{sf6_path}/reframework/data/{replay_name}", 'r') as replay_data_file:
                replay_data = json.load(replay_data_file)
            loaded_file = True
        except json.decoder.JSONDecodeError as e:
            # file probably not finished updating
            pass

    # dicts to be transformed into dataframes
    rounds = {}

    for round_number, round_data in replay_data.items():
        # if round number
        if round_number.isnumeric():
            # create dict for the round
            rounds.setdefault(int(round_number), {})
            # for each frame
            for frame_idx, frame_data in round_data.items():
                row_data = {}

                # append the player_tag to the key to create a unique column name
                for player_tag, player_data in frame_data.items():
                    row_data.update({f"{player_tag}_{key}": value for key, value in player_data.items() if
                                     key in keep_columns.keys()})
                # append the row dict
                rounds[int(round_number)][int(frame_idx)] = row_data

    # dict to store round dataframes
    rounds_df = {}
    for round_num, data in rounds.items():
        # create the df
        df = pd.DataFrame(data).T
        df.sort_index(inplace=True)

        # cast columns to type
        for col_name, col_type in keep_columns.items():
            for col in df.columns:
                if col_name in col:
                    df[col] = df[col].astype(col_type)
            rounds_df[round_num] = df

    # create dict to store player character names
    player_character = {}

    # for each player character
    for player_tag, player_id in replay_data['player_data'].items():
        # set player number
        player_num = 0 if '0' in player_tag else 1

        # load character name
        character_name = character_ids[str(player_id)]

        # set player character to appropriate character name
        player_character[str(player_num + 1)] = character_name

        # load move names
        with open(f"{character_move_names_path}/{character_name} Names.json", 'r') as character_move_names_file:
            character_move_names = json.load(character_move_names_file)

            for _, df in rounds_df.items():
                # create _actionName to store the name of moves based on _mActionId
                df[f"p{player_num + 1}_actionName"] = df[f"p{player_num + 1}_mActionId"].apply(
                    lambda x: character_move_names.get(f"{x:04}", np.nan))

                # create _actionStateName to store the name of moves based on _act_st
                df[f"p{player_num + 1}_actionStateName"] = df[f"p{player_num + 1}_act_st"].apply(
                    lambda x: act_st_names.get(f"{x}", np.nan))

    # columns to generate diff, to track changes in value across frames
    diff_columns = ['drive', 'current_HP']

    # for each diff column
    for diff_column in diff_columns:
        for round_num, df in rounds_df.items():
            for player_num in [1, 2]:
                # calc and create the dif fcolumn
                df[f'p{player_num}_{diff_column}_diff'] = df[f'p{player_num}_{diff_column}'].diff()

    return rounds_df, player_character


def create_damage_seq(p_idx, df):
    # create a boolean mask where act_st is 'damage'
    mask = df[f'p{p_idx}_actionStateName'] == 'DAMAGE'

    # identify the start of a new 'DAMAGE' sequence
    sequence_starts = mask != mask.shift()

    # assign a unique ID to each sequence
    sequence_ids = sequence_starts.cumsum()

    # identify where the value changes
    changes = sequence_ids.diff().ne(0).to_numpy()
    starts = np.where(changes)[0]

    # offset position by -1 for the end
    ends = np.where(changes)[0][1:] - 1

    # if the series starts with the same values, prepend the first index
    if not changes[0]:
        starts = np.insert(starts, 0, 0)

    # end of the last run is the end of the series
    ends = np.append(ends, len(sequence_ids) - 1)

    # create list of sequences
    damage_seqs = list(zip(starts, ends))

    return damage_seqs


def create_damage_stats(p_idx: str, damage_seqs: list, df: pd.DataFrame) -> Dict[str, Dict]:
    other_p_idx = "2" if p_idx == "1" else "1"
    damage_stats = {}

    for damage_seq in damage_seqs:
        total_damage = df.iloc[damage_seq[0]:damage_seq[1]][f'p{p_idx}_current_HP_diff'].sum()
        if total_damage < 0:
            # the entire attack sequence (combo), maybe used later
            player_attack_sequence = df.iloc[damage_seq[0]:damage_seq[1]][f'p{other_p_idx}_actionName'].unique()

            # create key for this actionName
            action_stats = damage_stats.setdefault(df.iloc[damage_seq[0]][f'p{other_p_idx}_actionName'],
                                                   {"count": 0, "total": 0})

            # increment the count by 1
            action_stats['count'] = action_stats['count'] + 1

            # accumulate the damage
            action_stats['total'] = action_stats['total'] + (total_damage * -1)

    return damage_stats


def create_action_counts(df):
    action_counts = {}
    for p_tag in ["1", "2"]:
        print(f"p_tag={p_tag}")
        # calculate a boolean mask where the actionName value changes
        mask = df[f'p{p_tag}_actionName'] != df[f'p{p_tag}_actionName'].shift()

        # cumsum to create a continuous sequence indicator
        df[f'p{p_tag}_actionName_sequence'] = mask.cumsum()

        # group by actionName and sequence and count occurrences
        sequence_counts = df.groupby([f'p{p_tag}_actionName', f'p{p_tag}_actionName_sequence']).size().reset_index(
            name='count')

        # count the number of sequences for each unique action name
        result = sequence_counts.groupby(f'p{p_tag}_actionName').size().reset_index(name='number_of_sequences')
        action_counts[p_tag] = result
    return action_counts


def generate_action_count(player_seq_counts, action_label, action_names, round_metrics, total_metrics):
    # store totals
    total_counts = {}

    # for each player and sequence count
    for p_tag, seq_count in player_seq_counts.items():
        # sum the count for these actions
        total_sequences = seq_count[seq_count[f'p{p_tag}_actionName'].isin(action_names)]['number_of_sequences'].sum()
        # store the total for that player
        total_counts[p_tag] = total_sequences

    # store total for this action
    round_metrics[action_label] = total_counts

    # create empty to store total
    action_total = total_metrics.setdefault(action_label, {"1": 0, "2": 0})

    # for each player
    for p_tag in total_counts:
        # sum the for this action
        action_total[p_tag] = action_total[p_tag] + round_metrics[action_label][p_tag]

    return round_metrics, total_metrics


def plot_player_damage(
        player_idx: str,
        round_num: int,
        data: Dict,
        player_character: Dict[str, str]):
    # round start at 0
    round_num = round_num + 1

    # reverse idx
    # TODO fix this issue when generating the player damage dicts
    player_idx = "2" if player_idx == "1" else "1"

    # extracting keys, counts, and totals
    moves = list(data.keys())
    counts = [data[move]["count"] for move in moves]
    totals = [data[move]["total"] for move in moves]

    # create a figure and plot
    fig, ax1 = plt.subplots(figsize=(15, 5))

    # bar position
    bar_width = 0.15
    index = np.arange(len(moves))

    # max counts for plot sizes
    max_count = max(counts)
    max_total = max(totals)

    # plot counts
    bars1 = ax1.bar(index - bar_width / 2, counts, bar_width, label="Count", alpha=0.8)

    # annotations for count
    for bar in bars1:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width() / 2, yval + 0.05 * max_count, round(yval, 2),
                 ha='center', va='bottom', color='white')

    # second Y axis for damage
    ax2 = ax1.twinx()
    bars2 = ax2.bar(index + bar_width / 2, totals, bar_width, label="Total Damage", alpha=0.8, color='orange')

    # annotations for damage
    x_offset = 0.17
    for bar in bars2:
        yval = bar.get_height()
        ax2.text(bar.get_x() + x_offset, yval / 2, round(yval),
                 ha='left', va='center', color='orange')

    # match bottom of both Y axes to 0
    ax1.set_ylim(bottom=0)

    # set y limit
    ax1.set_ylim(0, 1.3 * max_count)
    ax2.set_ylim(0, 1.3 * max_total)

    # use integer values for y axes
    ax2.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax1.yaxis.set_major_locator(MaxNLocator(integer=True))

    # labels, titles, and legends
    ax1.set_xlabel('')
    ax1.set_ylabel('Count', color='white')
    ax2.set_ylabel('Total Damage', color='orange')
    ax1.set_xticks(index)
    ax1.set_xticklabels(moves)
    ax1.legend(loc='upper left')
    ax2.legend(loc='upper right')
    plt.title(f'P{player_idx} ({player_character[player_idx]}) Round {round_num} Damage')

    # save plot to img
    plt.tight_layout()
    plt.savefig(f'stats_img/round{round_num}_player{player_idx}_dmg.png')
    plt.close()


def generate_drive_stats(p_idx: str, df: pd.DataFrame) -> Dict[str, Dict]:
    other_p_idx = "2" if p_idx == "1" else "1"
    drive_stats = {}

    for idx, row in df[df[f'p{p_idx}_drive_diff'] < 0].iterrows():
        # the action state name
        action_state_name = row[f'p{p_idx}_actionStateName']

        if action_state_name in ['DEF', 'DAMAGE']:
            # create if dict doesn't exist
            action_stats = drive_stats.setdefault(action_state_name, {})

            # total drive lost
            total_drive = action_stats.setdefault('total', 0)
            # accumulate total lost
            action_stats['total'] = total_drive + (row[f'p{p_idx}_drive_diff'] * -1)

            # create list if doesn't exist
            enemy_action_stats = action_stats.setdefault(row[f'p{other_p_idx}_actionName'], {"count": 0, "total": 0})
            # track for this action
            enemy_action_stats['count'] = enemy_action_stats['count'] + 1
            enemy_action_stats['total'] = enemy_action_stats['total'] + (row[f'p{p_idx}_drive_diff'] * -1)
        elif action_state_name == 'SPECIAL':
            action_name = row[f'p{p_idx}_actionName']
            action_stats = drive_stats.setdefault(action_name, {"count": 0, "total": 0})

            # track for this action
            action_stats['count'] = action_stats['count'] + 1
            action_stats['total'] = action_stats['total'] + (row[f'p{p_idx}_drive_diff'] * -1)

    return drive_stats


def plot_drive_data(data, round_num, player_character):
    abilities = {}

    for player, player_data in data.items():
        for ability, ability_data in player_data.items():
            if ability not in abilities:
                abilities[ability] = {}
            abilities[ability][player] = ability_data["total"]

    labels = list(abilities.keys())
    player0_vals = [abilities[ability].get("1", 0) for ability in labels]
    player1_vals = [abilities[ability].get("2", 0) for ability in labels]

    x = np.arange(len(labels))  # the label locations
    width = 0.35  # the width of the bars

    fig, ax = plt.subplots(figsize=(15, 5))
    rects1 = ax.bar(x - width / 2, player0_vals, width, label=f'P1 ({player_character["1"]})')
    rects2 = ax.bar(x + width / 2, player1_vals, width, label=f'P2 ({player_character["2"]})')

    # annotations to bars
    def add_annotations(rects):
        for rect in rects:
            height = rect.get_height()
            ax.annotate('{}'.format(int(height)),
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 3),  # 3 points vertical offset
                        textcoords="offset points",
                        ha='center', va='bottom')

    add_annotations(rects1)
    add_annotations(rects2)

    # labels, title, tick labels
    ax.set_ylabel('Drive')
    ax.set_title('Drive Gauge Usage/Lost')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()

    fig.tight_layout()
    plt.savefig(f'stats_img/round{round_num}_drive.png')
    plt.close()


def plot_table_metrics(data):
    fig, ax = plt.subplots(figsize=(15, 5))
    ax.axis('off')

    headers = [""]
    for round_key in sorted(data.keys()):
        round_num = int(round_key) + 1
        headers.extend([f"Round {round_num} Player 1", f"Round {round_num} Player 2"])
    headers.extend(["Total Player 1", "Total Player 2"])
    cell_data = [headers]

    for metric in data['0'].keys():
        row = [metric]
        for round_key in sorted(data.keys()):
            for player in ["1", "2"]:
                row.append(data[round_key][metric][player])
        total_player_1 = sum([data[round_key][metric]['1'] for round_key in data.keys()])
        total_player_2 = sum([data[round_key][metric]['2'] for round_key in data.keys()])
        row.extend([total_player_1, total_player_2])
        cell_data.append(row)

    # Calculate padding based on figure dimensions
    padding_inch = 1
    width_padding_fraction = padding_inch / fig.get_figwidth()
    height_padding_fraction = padding_inch / fig.get_figheight()

    bbox_left = width_padding_fraction
    bbox_bottom = height_padding_fraction
    bbox_width = 1 - 2 * width_padding_fraction
    bbox_height = 1 - 2 * height_padding_fraction

    table = ax.table(cellText=cell_data, loc='center', cellLoc='center',
                     bbox=[bbox_left, bbox_bottom, bbox_width, bbox_height])
    table.auto_set_font_size(False)
    table.set_fontsize(10)

    col_count = len(headers)
    table.auto_set_column_width(col=list(range(col_count)))
    table.scale(1, 0.5)  # Here's the adjustment for the row height

    header_color = "#505050"
    metric_color = "#A0A0A0"

    for key, cell in table.get_celld().items():
        if key[0] == 0:
            cell.set_facecolor(header_color)
            cell.set_text_props(color='white')
        else:
            cell.set_facecolor(metric_color)
            cell.set_text_props(color='black')

    plt.title('Match Stats')
    plt.tight_layout()
    plt.savefig(f'stats_img/match_stats.png')
    plt.close()


def update_plots(rounds_df, player_character):
    rounds_metrics = {}
    total_metrics = {}

    for round_num, df in rounds_df.items():
        drive_round_stats = {}
        for _, p_id in enumerate(["2", "1"]):
            damage_seq = create_damage_seq(p_id, df)
            damage_stats = create_damage_stats(p_id, damage_seq, df)
            if len(damage_stats) > 0:
                plot_player_damage(p_id, round_num, damage_stats, player_character)

            drive_stats = generate_drive_stats(p_id, df)
            drive_round_stats[p_id] = drive_stats
        plot_drive_data(drive_round_stats, round_num, player_character)

        action_counts = create_action_counts(df)
        round_metrics = rounds_metrics.setdefault(str(round_num), {})

        generate_action_count(action_counts, 'Perfect Parries', ["DPA_H(1)", "DPA_M(1)", "DPA_L(1)"], round_metrics,
                              total_metrics)

        generate_action_count(action_counts, 'Raw Drive Rushes', ["ATK_CTA_DASH"], round_metrics, total_metrics)

        generate_action_count(action_counts, 'Throw Breaks', ["NGE"], round_metrics, total_metrics)

        plot_table_metrics(rounds_metrics)


def main():
    rounds_df, player_character = load_recent_file(replay_dir)

    update_plots(rounds_df, player_character)
    print("updated plots")

    while True:
        print("watching file...")
        watch_file_for_changes(filename=f"{replay_dir}/{replay_name}")
        rounds_df, player_character = load_recent_file(replay_dir)
        update_plots(rounds_df, player_character)
        print("updated plots.")


if __name__ == "__main__":
    main()
