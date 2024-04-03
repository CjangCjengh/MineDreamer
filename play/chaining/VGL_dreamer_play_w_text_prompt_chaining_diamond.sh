#!/bin/bash

CONFIG_PATH="minedreamer/play/config/chaining/diamond.yaml"
PRIOR_WEIGHTS_DIR="data/weights/cvae"
SAVE_VIDEO_DIR="data/play/chaining/dreamer/diamond6"

vglrun /opt/conda/envs/minerl/bin/python minedreamer/play/chaining/dreamer_play_w_text_prompt_chaining_diamond.py \
--config ${CONFIG_PATH} \
--prior_weights_dir ${PRIOR_WEIGHTS_DIR} \
--save_video_dir ${SAVE_VIDEO_DIR} \
--times 50 \