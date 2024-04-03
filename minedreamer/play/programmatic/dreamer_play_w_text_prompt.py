import argparse
import os
import torch

from tqdm import tqdm
from minedreamer.config import CVAE_INFO, DEVICE, DREAMER_IMAGE_SIZE, FPS
from minedreamer.text_alignment.cvae import load_cvae_model
from minedreamer.results.programmatic_eval import ProgrammaticEvaluator
from minedreamer.utils.cmd_utils import custom_init_env
from minedreamer.utils.embed_utils import embed_one_frame, get_cvae_embed_from_text_instruction_with_current_and_goal_image_embed
from minedreamer.utils.file_utils import read_config, save_frame_as_image, save_json
from minedreamer.utils.mineclip_agent_env_utils import make_dreamer, load_mineclip_agent_env, setup_env_seed
from minedreamer.utils.text_overlay_utils import create_video_frame_w_prompt_on_frame
from minedreamer.utils.video_utils import save_frames_as_video


def play(args, metadata):
    text_prompt = args.text_prompt

    agent, mineclip, env = load_mineclip_agent_env(args.in_model, args.in_weights, args.env_seed, args.cond_scale, args.inventory, args.preferred_spawn_biome)
    goal_dreamer = make_dreamer(args.dreamer_url)
    CVAE_INFO["model_path"] = args.prior_weights_path
    cvae = load_cvae_model(CVAE_INFO)

    obs = env.reset()
    env.seed(args.env_seed)
    obs, _, _, _ = custom_init_env(env, args)

    # Setup
    gameplay_frames = []
    prog_evaluator = ProgrammaticEvaluator(obs)
    frame = obs['pov']

    current_image_save_dir = os.path.join(args.save_video_dir, "current")
    goal_image_save_dir = os.path.join(args.save_video_dir, "goal")
    obs_image_save_dir = os.path.join(args.save_video_dir, "obs")

    os.makedirs(current_image_save_dir, exist_ok=True)
    os.makedirs(goal_image_save_dir, exist_ok=True)
    os.makedirs(obs_image_save_dir, exist_ok=True)

    for i in tqdm(range(args.gameplay_length)):

        if i % args.freq == 0:
            
            current_image_embed = embed_one_frame(frame, mineclip, DEVICE)
            save_frame_as_image(frame, current_image_save_dir, f"{i}.png", target_size=DREAMER_IMAGE_SIZE, to_bgr=True)

            goal_image_list = goal_dreamer.generate_goal_image(suffix="goal_image", text_prompt=text_prompt, current_image_path=os.path.join(current_image_save_dir, f"{i}.png"), is_del=1)
            goal_image_embed = embed_one_frame(goal_image_list[0], mineclip, DEVICE)
            save_frame_as_image(goal_image_list[0], goal_image_save_dir, f"{i}.png", target_size=DREAMER_IMAGE_SIZE, to_bgr=False)

            with torch.cuda.amp.autocast():
                prompt_embed = get_cvae_embed_from_text_instruction_with_current_and_goal_image_embed(text_prompt, current_image_embed, goal_image_embed, mineclip, cvae, DEVICE)

        with torch.cuda.amp.autocast():
            minerl_action = agent.get_action(obs, prompt_embed)
        # execute action
        obs, _, _, _ = env.step(minerl_action)
        frame = obs['pov']

        if i % 20 == 0:
            save_frame_as_image(frame, obs_image_save_dir, f"{i}.png", target_size=DREAMER_IMAGE_SIZE, to_bgr=True) 

        # frame = cv2.resize(frame, (128, 128))
        frame_w_prompt_on_frame = create_video_frame_w_prompt_on_frame(frame, text_prompt, i, obs['location_stats'])
        gameplay_frames.append(frame_w_prompt_on_frame)

        prog_evaluator.update(obs)

    # Make the eval episode dir and save it
    save_frames_as_video(gameplay_frames, os.path.join(args.save_video_dir, f'{text_prompt}.mp4'), FPS, to_bgr=False)

    # Print the programmatic eval task results at the end of the gameplay
    metadata["results"] = prog_evaluator.get_results()
    prog_evaluator.print_results()


def update_args_with_config(args, config):
    args.in_model = config['model'].get('in_model', 'data/weights/vpt/2x.model')
    args.in_weights = config['model'].get('in_weights', 'data/weights/steve1/steve1.weights')
    args.cond_scale = float(config['conditioning'].get('cond_scale', 6.0))
    args.env_seed = config['environment'].get('env_seed', -1)
    args.gameplay_length = int(config['gameplay'].get('gameplay_length', 3000))
    args.dreamer_url = config['dreamer'].get('dreamer_url', "http://127.0.0.1:8000/")
    args.freq = int(config['frequency'].get('freq', 25))
    args.text_prompt = config['prompt']['text_prompt']
    args.preferred_spawn_biome = config['environment'].get('preferred_spawn_biome', None)
    args.inventory = config['environment'].get('inventory', None)
    args.custom_init_commands = config['environment'].get('custom_init_commands', [])
    args.summon_mobs = config['environment'].get('summon_mobs', [])
    return args


def main(args):

    text_prompt = args.text_prompt
    if isinstance(args.env_seed, int):
        args.env_seed = setup_env_seed(args.env_seed)
        for i in range(args.times):
            args.env_seed += 1

            args.save_dirpath = 'data/play/programmatic/dreamer/dreamer_' + str(text_prompt.replace(' ', '_')) + '_freq_' + str(args.freq) + '_cond_scale_' + str(args.cond_scale) + '_length_' + str(args.gameplay_length) + '_seed_' + str(args.env_seed)
            os.makedirs(args.save_dirpath, exist_ok=True)
            
            print(f'\nGenerating video for text prompt with name: {text_prompt}')
            args.save_video_dir = os.path.join(args.save_dirpath, text_prompt.replace(' ', '_'))
            metadata = vars(args)

            play(args, metadata)

            metadata_name = text_prompt.replace(' ', '_')
            save_json(metadata, os.path.join(args.save_video_dir, f'{metadata_name}.json'))
    elif isinstance(args.env_seed, list):
        env_seed_list = args.env_seed
        for env_seed in env_seed_list:
            args.env_seed = setup_env_seed(env_seed)

            args.save_dirpath = 'data/play/programmatic/dreamer/dreamer_' + str(text_prompt.replace(' ', '_')) + '_freq_' + str(args.freq) + '_cond_scale_' + str(args.cond_scale) + '_length_' + str(args.gameplay_length) + '_seed_' + str(args.env_seed)
            os.makedirs(args.save_dirpath, exist_ok=True)
            
            print(f'\nGenerating video for text prompt with name: {text_prompt}')
            args.save_video_dir = os.path.join(args.save_dirpath, text_prompt.replace(' ', '_'))
            metadata = vars(args)

            play(args, metadata)

            metadata_name = text_prompt.replace(' ', '_')
            save_json(metadata, os.path.join(args.save_video_dir, f'{metadata_name}.json'))
        


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, help='Path to the config file.')
    parser.add_argument('--prior_weights_path', type=str, help='Path to the prior model name.')
    parser.add_argument('--times', type=int, default=1)

    args = parser.parse_args()

    config = read_config(args.config)
    args = update_args_with_config(args, config)

    args_dict = vars(args)
    print("Args Value:")
    for arg_name in args_dict:
        print(f">>> '{arg_name}': {args_dict[arg_name]}")

    main(args)
