import gym
from gym import spaces

import airsim
from airgym.envs.airsim_env import AirSimEnv

import numpy as np
import math
import time
import random
from PIL import Image
from argparse import ArgumentParser


class AirSimDroneEnv(AirSimEnv):

    def __init__(self, ip_address, step_length, image_shape, destination):
        super().__init__(image_shape)
        self.step_length = step_length
        self.image_shape = image_shape
        self.destination = destination
        # self.middle_pixel = 0
        self.total_rewards = float(0.0)
        self.distance = 300.0
        self.pass1 = False
        self.pass2 = False
        self.pass3 = False

        #NED coordinate system (X,Y,Z) : +X is North, +Y is East and +Z is Down
        self.MAX_ALTITUDE = -60
        self.AVERAGE_ALTITUDE = -30
        self.MIN_ALTITUDE = -10
        self.MAX_SOUTH =  -60
        self.MAX_NORTH = 250
        self.MAX_LEFT = -60
        self.MAX_RIGHT = 60

        # self.action_space = spaces.Discrete(6)    
        self.action_space = spaces.Discrete(4)

        # self.observation_space = spaces.Dict({ 'depth_cam': spaces.Box(low=0, high=255, shape=(84, 84, 1)),
        #                                        'position': spaces.Box(low=-60, high=250, shape=(3,)) })
        #                                     #    'collision' : spaces.Discrete(2) })
        
        self.state = {'position': np.zeros(3),
                      'collision': False,
                      'prev_position': np.zeros(3) }

        self.drone = airsim.MultirotorClient(ip=ip_address)
        self._setup_flight()
        self.image_request = airsim.ImageRequest(
            3, airsim.ImageType.DepthPerspective, True, False
        )


    def __del__(self):
        self.drone.reset()


    def _setup_flight(self):
        self.drone.reset()
        self.drone.enableApiControl(True)
        self.drone.armDisarm(True)
    

    def _setup_starting_position(self):
        # Set starting position and velocity
        self.drone.moveToPositionAsync(0, 0, -30, 5).join()
        self.drone.moveByVelocityAsync(1, 0, 0, 5).join()


    # def _setup_destination(self):
    #     #random area a,b,c (ratio 1:2:3)
    #     area = random.randrange(1,7) # a -> 1 | b -> 2,3 | c -> 4,5,6
    #     if area < 2: # a
    #         x = random.randrange(230,271)
    #         y = random.randrange(45,71)
    #         print("\nDestination A ", [x,y,self.AVERAGE_ALTITUDE])
    #     elif area < 4: # b
    #         x = random.randrange(290,351)
    #         y = random.randrange(-75,-44)
    #         print("\nDestination B ", [x,y,self.AVERAGE_ALTITUDE])
    #     else: # c
    #         x = random.randrange(450,516)
    #         y = random.randrange(-75,56)
    #         print("\nDestination C ", [x,y,self.AVERAGE_ALTITUDE])


    #     return np.array([x,y,self.AVERAGE_ALTITUDE])


    def transform_obs(self, responses):
        img1d = np.array(responses[0].image_data_float, dtype=np.float)
        img1d = np.where(img1d > 255, 255, img1d)
        img2d = np.reshape(img1d, (responses[0].height, responses[0].width))


        image = Image.fromarray(img2d)
        im_final = np.array(image.resize((84, 84)).convert("L"))

        return im_final.reshape([84, 84, 1])


    def _get_obs(self):
        responses = self.drone.simGetImages([self.image_request])
        image = self.transform_obs(responses)
        self.drone_state = self.drone.getMultirotorState()

        self.state["prev_position"] = self.state["position"]
        self.state["position"] = self.drone_state.kinematics_estimated.position
        self.state["velocity"] = self.drone_state.kinematics_estimated.linear_velocity

        collision = self.drone.simGetCollisionInfo().has_collided
        self.state["collision"] = collision

        return image


    def _do_action(self, action):
        quad_offset = self.interpret_action(action)
        quad_vel = self.drone.getMultirotorState().kinematics_estimated.linear_velocity
        self.drone.moveByVelocityAsync(
            quad_vel.x_val + quad_offset[0],
            quad_vel.y_val + quad_offset[1],
            # quad_vel.z_val + quad_offset[2],
            0,
            4,
        ).join()
    

    def _compute_reward(self, action):
        rewards = float(0.0)
        done = False

        if self.state["collision"]: # collide
            rewards = -100
            done = True
        elif self.state["position"].x_val < -80 or self.state["position"].y_val > 80 or self.state["position"].y_val < -80 :
            done = True
        elif self.state["position"].x_val > 200:
            rewards = 25
            done = True
        elif self.state["position"].x_val > 150 and not self.pass3:
            rewards = 25
            self.pass3 = True
        elif self.state["position"].x_val > 100 and not self.pass2:
            rewards = 25
            self.pass2 = True
        elif self.state["position"].x_val > 50 and not self.pass1:
            rewards = 25
            self.pass1 = True

        return rewards, done


    def step(self, action):
        self._do_action(action)
        obs = self._get_obs()
        reward, done = self._compute_reward(action)

        # if done:

        #     self.total_rewards = 0
            

        if action == 0:
            movement = 'fore'
        elif action == 1:
            movement = 'back'
        elif action == 2:
            movement = 'right'
        else:
            movement = 'left'


        # print("reward ", format(reward, ".2f"),  "\t  done  " + str(done), "\t action ", movement, "\t    velocity [", format(self.state["velocity"].x_val, ".1f"), ",\t",  format(self.state["velocity"].y_val, ".1f"), ",\t" , format(self.state["velocity"].z_val, ".1f"), "]")
        # print("reward ", format(reward, ".2f"),  "\t  done  " + str(done), "\t action ", movement, "\t    position [", format(self.state["position"].x_val, ".1f"), ",\t",  format(self.state["position"].y_val, ".1f"), ",\t" , format(self.state["position"].z_val, ".1f"), "]")
        print("reward ", format(reward, ".0f"),  "\t  done  " + str(done), "\t action ", movement)
        if done:
            self.pass1 = False
            self.pass2 = False
            self.pass3 = False
            print('Done!\n')

        # if done:
        #     self.total_rewards = 0
        #     if self.done_flag == 0:
        #         print("done : collision")
        #     elif self.done_flag == 1:
        #         print("done : out of range")
        #         print("destination : ", self.destination, "\tposition : [", format(self.state["position"].x_val, ".1f"), ",",  format(self.state["position"].y_val, ".1f"), "," , format(self.state["position"].z_val, ".1f"), "]" )
        #     elif self.done_flag == 2:
        #         print("done : reach destination")
        #     else:
        #         print("done : total rewards < -100")
        #     self.done_flag = -1

        # if done:
        #     if self.state["collision"]:
        #         print('collision\n')
        #     else:
        #         print("out of range -> position : [", format(self.state["position"].x_val, ".1f"), ",",  format(self.state["position"].y_val, ".1f"), "," , format(self.state["position"].z_val, ".1f"), "]\n"  )

        return obs, reward, done, self.state


    def reset(self):
        # self.destination = self._setup_destination()
        self.distance = 300.0
        self._setup_flight()
        self._setup_starting_position()
        return self._get_obs()


    def interpret_action(self, action):
        #NED coordinate system (X,Y,Z) : +X is North, +Y is East and +Z is Down
        # if action == 0: # forward
        #     quad_offset = (self.step_length, 0, 0)
        #     self.movement = 'fore'
        # elif action == 1: # slide right
        #     quad_offset = (0, self.step_length, 0)
        #     self.movement = 'right'
        # elif action == 2: # downward
        #     quad_offset = (0, 0, self.step_length)
        #     self.movement = 'down'
        # elif action == 3: # backward
        #     quad_offset = (-self.step_length, 0, 0)
        #     self.movement = 'back'
        # elif action == 4: # slide left
        #     quad_offset = (0, -self.step_length, 0)
        #     self.movement = 'left'
        # elif action == 5: # upward
        #     quad_offset = (0, 0, -self.step_length)
        #     self.movement = 'up'


        if action == 0: # forward
            quad_offset = (self.step_length, 0, 0)
        elif action == 1: # back
            quad_offset = (-self.step_length, 0, 0)
        elif action == 2: # slide right
            quad_offset = (0, self.step_length, 0)
        elif action == 3: # slide left
            quad_offset = (0, -self.step_length, 0)

        return quad_offset
